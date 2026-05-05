"""IAgentModel implementation backed by vLLM."""

from collections.abc import AsyncIterator, Mapping, Sequence
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
from spakky.plugins.vllm.error import VllmResponseError


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
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Return the streaming surface reserved for the follow-up mapper."""
        return self._stream_not_implemented(request)

    async def _stream_not_implemented(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        self._to_chat_completion_payload(request, stream=True)
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=ModelError(
                code="vllm_streaming_not_implemented",
                message="vLLM streaming mapper is not implemented yet",
                retryable=False,
                metadata={"provider": "vllm"},
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)

    def _to_chat_completion_payload(
        self,
        request: ModelRequest,
        *,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.__config.model,
            "messages": [
                self._to_openai_message(message) for message in request.messages
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
        message = self._expect_mapping(first_choice.get("message"))
        content = message.get("content")
        if not isinstance(content, str):
            raise VllmResponseError
        tool_calls = tuple(self._to_tool_calls(message.get("tool_calls")))
        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=self._to_usage(response.get("usage")),
            metadata={"provider": "vllm"},
        )

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
