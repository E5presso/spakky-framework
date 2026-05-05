"""IAgentModel implementation backed by vLLM."""

from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError, loads
from typing import override

from spakky.agent import (
    IAgentModel,
    JsonObject,
    JsonValue,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelUsage,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.vllm.client import IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    AbstractVllmError,
    VllmModelRefusalError,
    VllmResponseError,
    VllmStreamingDisabledError,
    VllmTimeoutError,
    VllmTransportError,
)


@dataclass(slots=True)
class _ToolCallBuffer:
    index: int
    call_id: str | None = None
    name: str | None = None
    arguments_fragments: list[str] = field(default_factory=list)

    def extend_arguments(self, fragment: str | None) -> None:
        if fragment is not None:
            self.arguments_fragments.append(fragment)

    def to_tool_call(self, adapter: "VllmAgentModel") -> ModelToolCall:
        if self.name is None:
            raise VllmResponseError
        provider_arguments = "".join(self.arguments_fragments)
        return ModelToolCall(
            name=self.name,
            arguments=adapter._to_tool_arguments(provider_arguments),
            call_id=self.call_id,
            metadata={"provider_arguments": provider_arguments},
        )


@Pod()
class VllmAgentModel(IAgentModel):
    """Spakky Agent model adapter for a local OpenAI-compatible vLLM server."""

    __config: VllmConfig
    __client: IVllmChatClient

    def __init__(self, config: VllmConfig, client: IVllmChatClient) -> None:
        self.__config = config
        self.__client = client

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a provider-neutral model response from vLLM chat completions."""
        payload = self._to_chat_completion_payload(request, stream=False)
        response = await self.__client.complete(payload, self.__config)
        return self._to_model_response(response)

    @override
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelStreamEvent, None]:
        """Return provider-neutral stream events from vLLM chat completions."""
        return self._stream(request)

    async def _stream(
        self,
        request: ModelRequest,
    ) -> AsyncGenerator[ModelStreamEvent, None]:
        if not self.__config.stream_enabled:
            yield self._to_error_event(VllmStreamingDisabledError())
            yield self._done_event(None, None)
            return

        payload = self._to_chat_completion_payload(request, stream=True)
        tool_buffers: dict[int, _ToolCallBuffer] = {}
        finish_reason: str | None = None
        usage: ModelUsage | None = None
        terminal_error: ModelError | None = None
        try:
            stream = self.__client.stream(payload, self.__config)
        except AbstractVllmError as e:
            yield self._to_error_event(e)
            yield self._done_event(None, None)
            return
        try:
            async for chunk in stream:
                provider_error = self._to_provider_error(chunk.get("error"))
                if provider_error is not None:
                    terminal_error = provider_error
                    break
                usage_value = chunk.get("usage")
                if usage_value is not None:
                    usage = self._to_usage(usage_value)
                choices = self._expect_sequence(chunk.get("choices"))
                if len(choices) == 0:
                    continue
                for raw_choice in choices:
                    choice = self._expect_mapping(raw_choice)
                    async for event in self._stream_choice_events(
                        choice,
                        tool_buffers,
                    ):
                        yield event
                    choice_finish_reason = self._optional_string(
                        choice.get("finish_reason")
                    )
                    if choice_finish_reason is not None:
                        finish_reason = choice_finish_reason
                        if finish_reason == "tool_calls":
                            for event in self._tool_call_events(tool_buffers):
                                yield event
                        terminal_error = self._finish_reason_error(finish_reason)
        except AbstractVllmError as e:
            yield self._to_error_event(e)
            yield self._done_event(None, None)
            return
        finally:
            await stream.aclose()

        if terminal_error is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=terminal_error,
            )
        yield self._done_event(finish_reason, usage)

    def _to_chat_completion_payload(
        self,
        request: ModelRequest,
        *,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.__config.model,
            "messages": [
                self._to_openai_message(message)
                for message in request.assemble_messages()
            ],
            "stream": stream,
        }
        if request.sampling.temperature is not None:
            payload["temperature"] = request.sampling.temperature
        if request.sampling.top_p is not None:
            payload["top_p"] = request.sampling.top_p
        if request.sampling.max_tokens is not None:
            payload["max_tokens"] = request.sampling.max_tokens
        if request.structured_output is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": (
                        request.structured_output.output_type_name
                        or "structured_output"
                    ),
                    "schema": dict(request.structured_output.constraint.schema),
                    "strict": request.structured_output.constraint.strict,
                },
            }
        if request.tool_calling is not None:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": dict(tool.parameters.schema),
                    },
                }
                for tool in request.tool_calling.tools
            ]
            payload["tool_choice"] = self._to_tool_choice(request.tool_calling.choice)
        if stream and request.streaming.include_usage:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _to_openai_message(self, message: ModelMessage) -> dict[str, object]:
        role = message.role.value
        if message.role == ModelMessageRole.EVIDENCE:
            role = ModelMessageRole.USER.value
        return {"role": role, "content": message.content}

    def _to_tool_choice(self, choice: ModelToolChoice) -> str:
        return {
            ModelToolChoice.AUTO: "auto",
            ModelToolChoice.NONE: "none",
            ModelToolChoice.REQUIRED: "required",
        }[choice]

    def _to_model_response(self, response: Mapping[str, object]) -> ModelResponse:
        choices = self._expect_sequence(response.get("choices"))
        if len(choices) == 0:
            raise VllmResponseError
        first_choice = self._expect_mapping(choices[0])
        finish_reason = self._optional_string(first_choice.get("finish_reason"))
        message = self._expect_mapping(first_choice.get("message"))
        refusal = self._optional_string(message.get("refusal"))
        if refusal is not None and refusal != "":
            raise VllmModelRefusalError
        if finish_reason == "content_filter":
            raise VllmModelRefusalError
        tool_calls = tuple(self._to_tool_calls(message.get("tool_calls")))
        content = self._to_message_content(message.get("content"), tool_calls)
        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=self._to_usage(response.get("usage")),
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    async def _stream_choice_events(
        self,
        choice: Mapping[str, object],
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> AsyncIterator[ModelStreamEvent]:
        delta_value = choice.get("delta")
        if delta_value is None:
            return
        delta = self._expect_mapping(delta_value)
        content = self._optional_string(delta.get("content"))
        if content is not None and content != "":
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta=content,
                metadata={"provider": "vllm"},
            )
        refusal = self._optional_string(delta.get("refusal"))
        if refusal is not None and refusal != "":
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(
                    code="model_refusal",
                    message=refusal,
                    retryable=False,
                    metadata={"provider": "vllm"},
                ),
            )
        tool_call_chunks = delta.get("tool_calls")
        if tool_call_chunks is not None:
            self._accumulate_tool_call_chunks(tool_call_chunks, tool_buffers)

    def _accumulate_tool_call_chunks(
        self,
        value: object,
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> None:
        raw_calls = self._expect_sequence(value)
        for position, raw_call in enumerate(raw_calls):
            item = self._expect_mapping(raw_call)
            index = self._optional_int(item.get("index"))
            if index is None:
                index = position
            buffer = tool_buffers.setdefault(index, _ToolCallBuffer(index=index))
            call_id = self._optional_string(item.get("id"))
            if call_id is not None:
                buffer.call_id = call_id
            function_value = item.get("function")
            if function_value is None:
                continue
            function = self._expect_mapping(function_value)
            name = self._optional_string(function.get("name"))
            if name is not None:
                buffer.name = name
            buffer.extend_arguments(self._optional_string(function.get("arguments")))

    def _tool_call_events(
        self,
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> tuple[ModelStreamEvent, ...]:
        events = tuple(
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=tool_buffers[index].to_tool_call(self),
                metadata={"provider": "vllm"},
            )
            for index in sorted(tool_buffers)
        )
        tool_buffers.clear()
        return events

    def _to_provider_error(self, value: object) -> ModelError | None:
        if value is None:
            return None
        error = self._expect_mapping(value)
        code = self._optional_string(error.get("code")) or "provider_error"
        message = self._optional_string(error.get("message")) or "vLLM stream error"
        return ModelError(
            code=code,
            message=message,
            retryable=False,
            metadata={"provider": "vllm"},
        )

    def _finish_reason_error(self, finish_reason: str) -> ModelError | None:
        if finish_reason in ("stop", "tool_calls"):
            return None
        code = (
            "model_refusal"
            if finish_reason == "content_filter"
            else "model_finish_reason"
        )
        return ModelError(
            code=code,
            message=f"vLLM stream finished with reason: {finish_reason}",
            retryable=False,
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    def _to_error_event(self, error: AbstractVllmError) -> ModelStreamEvent:
        return ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=self._to_model_error(error),
        )

    def _to_model_error(self, error: AbstractVllmError) -> ModelError:
        if isinstance(error, VllmTimeoutError):
            return ModelError(
                code="vllm_timeout",
                message=VllmTimeoutError.message,
                retryable=True,
                metadata={"provider": "vllm"},
            )
        if isinstance(error, VllmTransportError):
            return ModelError(
                code="vllm_transport_error",
                message=VllmTransportError.message,
                retryable=True,
                metadata={"provider": "vllm"},
            )
        if isinstance(error, VllmStreamingDisabledError):
            return ModelError(
                code="vllm_streaming_disabled",
                message=VllmStreamingDisabledError.message,
                retryable=False,
                metadata={"provider": "vllm"},
            )
        return ModelError(
            code="vllm_response_error",
            message=VllmResponseError.message,
            retryable=False,
            metadata={"provider": "vllm"},
        )

    def _done_event(
        self,
        finish_reason: str | None,
        usage: ModelUsage | None,
    ) -> ModelStreamEvent:
        return ModelStreamEvent(
            kind=ModelStreamEventKind.DONE,
            usage=usage,
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    def _to_message_content(
        self,
        value: object,
        tool_calls: tuple[ModelToolCall, ...],
    ) -> str:
        if isinstance(value, str):
            return value
        if value is None and len(tool_calls) > 0:
            return ""
        raise VllmResponseError

    def _to_tool_calls(self, value: object) -> tuple[ModelToolCall, ...]:
        if value is None:
            return ()
        raw_calls = self._expect_sequence(value)
        calls: list[ModelToolCall] = []
        for raw_call in raw_calls:
            item = self._expect_mapping(raw_call)
            function = self._expect_mapping(item.get("function"))
            name = function.get("name")
            if not isinstance(name, str):
                raise VllmResponseError
            calls.append(
                ModelToolCall(
                    name=name,
                    arguments=self._to_tool_arguments(function.get("arguments")),
                    call_id=self._optional_string(item.get("id")),
                    metadata={
                        "provider_arguments": self._optional_string(
                            function.get("arguments")
                        )
                        or "",
                    },
                )
            )
        return tuple(calls)

    def _to_tool_arguments(self, value: object) -> JsonObject:
        raw_arguments = self._optional_string(value)
        if raw_arguments is None or raw_arguments == "":
            return {}
        try:
            decoded: object = loads(raw_arguments)
        except JSONDecodeError as e:
            raise VllmResponseError from e
        return self._to_json_object(decoded)

    def _to_json_object(self, value: object) -> JsonObject:
        if not isinstance(value, Mapping):
            raise VllmResponseError
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise VllmResponseError
            result[key] = self._to_json_value(item)
        return result

    def _to_json_value(self, value: object) -> JsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Mapping):
            return self._to_json_object(value)
        if isinstance(value, Sequence):
            return tuple(self._to_json_value(item) for item in value)
        raise VllmResponseError

    def _to_usage(self, value: object) -> ModelUsage:
        if value is None:
            return ModelUsage()
        usage = self._expect_mapping(value)
        return ModelUsage(
            input_tokens=self._optional_int(usage.get("prompt_tokens")),
            output_tokens=self._optional_int(usage.get("completion_tokens")),
            total_tokens=self._optional_int(usage.get("total_tokens")),
        )

    def _expect_mapping(self, value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise VllmResponseError
        return value

    def _expect_sequence(self, value: object) -> tuple[object, ...]:
        if not isinstance(value, list):
            raise VllmResponseError
        return tuple(value)

    def _optional_string(self, value: object) -> str | None:
        if value is None or isinstance(value, str):
            return value
        raise VllmResponseError

    def _optional_int(self, value: object) -> int | None:
        if value is None or isinstance(value, int):
            return value
        raise VllmResponseError
