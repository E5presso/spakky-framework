"""OpenAI SDK adapter for standard and vLLM chat-completions profiles."""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError, dumps
from os import environ
from typing import override

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    Omit,
    omit,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionStreamOptionsParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_tool_choice_option_param import (
    ChatCompletionToolChoiceOptionParam,
)
from openai.types.completion_usage import CompletionUsage
from openai.types.shared_params.response_format_json_schema import (
    ResponseFormatJSONSchema,
)
from spakky.agent import (
    JsonObject,
    JsonSchemaConstraint,
    JsonValue,
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

from spakky.plugins.llm.codec import LlmJsonCodec
from spakky.plugins.llm.config import (
    LlmProviderApi,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.constants import OFFICIAL_OPENAI_BASE_URL
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    ensure_terminal_tool_choice,
    ensure_tool_call_allowed,
    routing_metadata,
)

_SUCCESS_FINISH_REASONS = frozenset({"stop", "length", "tool_calls"})


@dataclass(slots=True)
class _ToolCallBuffer:
    """Accumulate one indexed streamed function call."""

    index: int
    call_id: str | None = None
    name: str | None = None
    argument_fragments: list[str] = field(default_factory=list)
    started: bool = False


@Pod()
class OpenAIChatProvider(ILLMProvider):
    """Map OpenAI SDK chat completions onto the Spakky model contract."""

    __codec: LlmJsonCodec

    def __init__(self) -> None:
        self.__codec = LlmJsonCodec()

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        """Return the OpenAI chat-completions API family."""
        return frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS})

    @property
    @override
    def is_default(self) -> bool:
        """Mark the first-party OpenAI adapter as replaceable default."""
        return True

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        """Return one normalized completion through the official async SDK."""
        try:
            async with self._client(target) as client:
                completion = await client.chat.completions.create(
                    model=target.model,
                    messages=self._messages(request),
                    stream=False,
                    temperature=self._optional_number(request.sampling.temperature),
                    top_p=self._optional_number(request.sampling.top_p),
                    max_tokens=self._legacy_max_tokens(target, request),
                    max_completion_tokens=self._standard_max_tokens(target, request),
                    tools=self._tools(request),
                    tool_choice=self._tool_choice(request),
                    response_format=self._response_format(request),
                    extra_body=self._extra_body(target, request),
                    timeout=target.profile.request_timeout_seconds,
                )
        except APIError as error:
            raise self._normalized_sdk_error(error) from error
        except JSONDecodeError as error:
            raise LlmResponseError from error
        try:
            return self._response(target, request, completion)
        except (AttributeError, TypeError) as error:
            raise LlmResponseError from error

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Return normalized events from an official SDK async stream."""
        return self._stream(target, request)

    async def _stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        constraints = self.__codec.tool_constraints(request.tool_calling)
        buffers: dict[int, _ToolCallBuffer] = {}
        structured_fragments: list[str] = []
        finish_reason: str | None = None
        usage: ModelUsage | None = None
        try:
            async with self._client(target) as client:
                stream = await client.chat.completions.create(
                    model=target.model,
                    messages=self._messages(request),
                    stream=True,
                    stream_options=self._stream_options(request),
                    temperature=self._optional_number(request.sampling.temperature),
                    top_p=self._optional_number(request.sampling.top_p),
                    max_tokens=self._legacy_max_tokens(target, request),
                    max_completion_tokens=self._standard_max_tokens(target, request),
                    tools=self._tools(request),
                    tool_choice=self._tool_choice(request),
                    response_format=self._response_format(request),
                    extra_body=self._extra_body(target, request),
                    timeout=target.profile.stream_timeout_seconds,
                )
                async with stream:
                    async for chunk in stream:
                        if request.streaming.include_usage and chunk.usage is not None:
                            usage = self._usage(chunk.usage)
                        async for event in self._chunk_events(
                            target,
                            request,
                            chunk,
                            constraints,
                            buffers,
                            structured_fragments,
                        ):
                            yield event
                        chunk_reason = self._finish_reason(chunk)
                        if chunk_reason is not None:
                            finish_reason = chunk_reason
        except APIError as error:
            raise self._normalized_sdk_error(error) from error
        except (JSONDecodeError, AttributeError, TypeError) as error:
            raise LlmResponseError from error

        if finish_reason is None:
            raise LlmResponseError
        if (len(buffers) > 0) != (finish_reason == "tool_calls"):
            raise LlmResponseError
        tool_calls = tuple(
            self._buffered_tool_call(target, buffers[index], constraints)
            for index in sorted(buffers)
        )
        ensure_terminal_tool_choice(request, len(tool_calls))
        structured_output: JsonValue = None
        if request.structured_output is not None:
            structured_output = self.__codec.decode_value(
                "".join(structured_fragments),
                request.structured_output.constraint,
            )
        for tool_call in tool_calls:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_END,
                tool_call=tool_call,
                metadata=self._metadata(target),
            )
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=tool_call,
                metadata=self._metadata(target),
            )
        if request.structured_output is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                structured_output=structured_output,
                metadata=self._metadata(target),
            )
        yield done_event(target, finish_reason, usage)

    async def _chunk_events(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        chunk: ChatCompletionChunk,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
        buffers: dict[int, _ToolCallBuffer],
        structured_fragments: list[str],
    ) -> AsyncIterator[ModelStreamEvent]:
        if len(chunk.choices) == 0:
            return
        choice = chunk.choices[0]
        delta = choice.delta
        if delta.refusal is not None and delta.refusal != "":
            raise LlmModelRefusalError
        if choice.finish_reason is not None:
            self._ensure_finish_reason(choice.finish_reason)
        if delta.content is not None and delta.content != "":
            structured_fragments.append(delta.content)
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta=delta.content,
                metadata=self._metadata(target),
            )
        reasoning = self._reasoning_delta(target, delta.model_extra)
        if reasoning is not None and reasoning != "":
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta=reasoning,
                metadata=self._metadata(target),
            )
        for tool_delta in delta.tool_calls or ():
            ensure_tool_call_allowed(request)
            buffer = buffers.setdefault(
                tool_delta.index,
                _ToolCallBuffer(index=tool_delta.index),
            )
            if tool_delta.id is not None:
                buffer.call_id = tool_delta.id
            if tool_delta.function is not None:
                if tool_delta.function.name is not None:
                    buffer.name = tool_delta.function.name
                if tool_delta.function.arguments is not None:
                    buffer.argument_fragments.append(tool_delta.function.arguments)
            name = buffer.name
            if name is None:
                continue
            if not buffer.started:
                buffer.started = True
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_START,
                    tool_call=self._partial_tool_call(target, buffer, name),
                    metadata=self._metadata(target),
                )
            if (
                buffer.started
                and tool_delta.function is not None
                and tool_delta.function.arguments is not None
            ):
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
                    tool_call=self._partial_tool_call(target, buffer, name),
                    tool_call_args_delta=tool_delta.function.arguments,
                    metadata=self._metadata(target),
                )

    def _client(self, target: LlmModelTarget) -> AsyncOpenAI:
        profile = target.profile
        if profile.api not in self.apis:
            raise LlmUnsupportedFeatureError
        if "OPENAI_CUSTOM_HEADERS" in environ:
            raise LlmConfigurationError
        if (
            profile.openai_dialect == OpenAICompatibleDialect.VLLM
            and profile.base_url is None
        ):
            raise LlmConfigurationError
        api_key = profile.api_key_value()
        if api_key is None:
            if profile.openai_dialect != OpenAICompatibleDialect.VLLM:
                raise LlmConfigurationError
            api_key = "not-required"
        return AsyncOpenAI(
            api_key=api_key,
            admin_api_key="",
            base_url=profile.base_url or OFFICIAL_OPENAI_BASE_URL,
            organization="",
            project="",
            webhook_secret="",
            timeout=profile.request_timeout_seconds,
            max_retries=profile.max_retries,
            default_headers=dict(profile.headers),
        )

    def _messages(self, request: ModelRequest) -> list[ChatCompletionMessageParam]:
        return [self._message(message) for message in request.assemble_messages()]

    def _message(self, message: ModelMessage) -> ChatCompletionMessageParam:
        if message.role == ModelMessageRole.SYSTEM:
            system: ChatCompletionSystemMessageParam = {
                "role": "system",
                "content": message.content,
            }
            return system
        if message.role in (ModelMessageRole.USER, ModelMessageRole.EVIDENCE):
            user: ChatCompletionUserMessageParam = {
                "role": "user",
                "content": message.content,
            }
            return user
        if message.role == ModelMessageRole.ASSISTANT:
            assistant: ChatCompletionAssistantMessageParam = {
                "role": "assistant",
                "content": message.content,
            }
            tool_calls = self._history_tool_calls(message.metadata)
            if tool_calls is not None:
                assistant["tool_calls"] = tool_calls
            return assistant
        call_id = message.metadata.get("call_id")
        if not isinstance(call_id, str) or call_id.strip() == "":
            raise LlmResponseError
        tool: ChatCompletionToolMessageParam = {
            "role": "tool",
            "content": message.content,
            "tool_call_id": call_id,
        }
        return tool

    def _history_tool_calls(
        self,
        metadata: JsonObject,
    ) -> list[ChatCompletionMessageFunctionToolCallParam] | None:
        value = metadata.get("tool_calls")
        if value is None:
            return None
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise LlmResponseError
        calls: list[ChatCompletionMessageFunctionToolCallParam] = []
        for raw_call in value:
            if not isinstance(raw_call, Mapping):
                raise LlmResponseError
            call_id = raw_call.get("id")
            name = raw_call.get("name")
            arguments = raw_call.get("arguments")
            if not isinstance(call_id, str) or not isinstance(name, str):
                raise LlmResponseError
            if isinstance(arguments, str):
                encoded_arguments = arguments
            elif isinstance(arguments, Mapping):
                encoded_arguments = dumps(arguments, separators=(",", ":"))
            else:
                raise LlmResponseError
            calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": encoded_arguments,
                    },
                }
            )
        return calls

    def _tools(self, request: ModelRequest) -> list[ChatCompletionToolParam] | Omit:
        if request.tool_calling is None:
            return omit
        if len(request.tool_calling.tools) == 0:
            raise LlmResponseError
        tools: list[ChatCompletionToolParam] = []
        for tool in request.tool_calling.tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": self._schema(tool.parameters.schema),
                        "strict": tool.parameters.strict,
                    },
                }
            )
        return tools

    def _tool_choice(
        self, request: ModelRequest
    ) -> ChatCompletionToolChoiceOptionParam | Omit:
        if request.tool_calling is None:
            return omit
        if request.tool_calling.choice == ModelToolChoice.AUTO:
            return "auto"
        if request.tool_calling.choice == ModelToolChoice.NONE:
            return "none"
        return "required"

    def _response_format(
        self, request: ModelRequest
    ) -> ResponseFormatJSONSchema | Omit:
        if request.structured_output is None:
            return omit
        return {
            "type": "json_schema",
            "json_schema": {
                "name": request.structured_output.output_type_name
                or "structured_output",
                "schema": self._schema(request.structured_output.constraint.schema),
                "strict": request.structured_output.constraint.strict,
            },
        }

    def _extra_body(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> dict[str, object] | None:
        profile = target.profile
        if profile.openai_dialect != OpenAICompatibleDialect.VLLM:
            return None
        extra: dict[str, object] = {}
        if len(target.route.chat_template_kwargs) > 0:
            extra["chat_template_kwargs"] = dict(target.route.chat_template_kwargs)
        if request.structured_output is not None:
            extra["structured_outputs"] = {
                "json": self._schema(request.structured_output.constraint.schema)
            }
        return extra or None

    def _response(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        completion: ChatCompletion,
    ) -> ModelResponse:
        if len(completion.choices) == 0:
            raise LlmResponseError
        choice = completion.choices[0]
        message = choice.message
        if message.refusal is not None and message.refusal != "":
            raise LlmModelRefusalError
        self._ensure_finish_reason(choice.finish_reason)
        constraints = self.__codec.tool_constraints(request.tool_calling)
        tool_call_items: list[ModelToolCall] = []
        for call in message.tool_calls or ():
            if call.type != "function":
                raise LlmUnsupportedFeatureError
            tool_call_items.append(self._tool_call(target, call, constraints))
        tool_calls = tuple(tool_call_items)
        if (len(tool_calls) > 0) != (choice.finish_reason == "tool_calls"):
            raise LlmResponseError
        ensure_terminal_tool_choice(request, len(tool_calls))
        if message.content is None:
            if len(tool_calls) == 0:
                raise LlmResponseError
            content = ""
        else:
            content = message.content
        structured_output: JsonValue = None
        if request.structured_output is not None:
            structured_output = self.__codec.decode_value(
                content,
                request.structured_output.constraint,
            )
        metadata: dict[str, JsonValue] = self._metadata(target)
        metadata.update(
            {
                "finish_reason": choice.finish_reason,
                "response_id": completion.id,
                "response_model": completion.model,
            }
        )
        reasoning = self._reasoning_delta(target, message.model_extra)
        if reasoning is not None:
            metadata["reasoning"] = reasoning
        return ModelResponse(
            content=content,
            structured_output=structured_output,
            tool_calls=tool_calls,
            usage=self._usage(completion.usage),
            metadata=metadata,
        )

    def _tool_call(
        self,
        target: LlmModelTarget,
        call: ChatCompletionMessageFunctionToolCall,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelToolCall:
        name = call.function.name
        arguments = call.function.arguments
        constraint = self.__codec.tool_constraint(name, constraints)
        return ModelToolCall(
            name=name,
            arguments=self.__codec.decode_object(arguments, constraint),
            call_id=call.id,
            metadata={
                **self._metadata(target),
                "provider_arguments": arguments,
            },
        )

    def _buffered_tool_call(
        self,
        target: LlmModelTarget,
        buffer: _ToolCallBuffer,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelToolCall:
        if buffer.name is None:
            raise LlmResponseError
        arguments = "".join(buffer.argument_fragments)
        constraint = self.__codec.tool_constraint(buffer.name, constraints)
        return ModelToolCall(
            name=buffer.name,
            arguments=self.__codec.decode_object(arguments, constraint),
            call_id=buffer.call_id,
            metadata={
                **self._metadata(target),
                "provider_arguments": arguments,
            },
        )

    def _partial_tool_call(
        self,
        target: LlmModelTarget,
        buffer: _ToolCallBuffer,
        name: str,
    ) -> ModelToolCall:
        return ModelToolCall(
            name=name,
            arguments={},
            call_id=buffer.call_id,
            metadata=self._metadata(target),
        )

    def _reasoning_delta(
        self,
        target: LlmModelTarget,
        extra: dict[str, object] | None,
    ) -> str | None:
        if not target.route.capability.supports_reasoning or extra is None:
            return None
        reasoning = extra.get("reasoning_content")
        if reasoning is None:
            reasoning = extra.get("reasoning")
        if reasoning is None or isinstance(reasoning, str):
            return reasoning
        raise LlmResponseError

    def _finish_reason(self, chunk: ChatCompletionChunk) -> str | None:
        if len(chunk.choices) == 0:
            return None
        return chunk.choices[0].finish_reason

    def _ensure_finish_reason(self, finish_reason: str) -> None:
        if finish_reason in _SUCCESS_FINISH_REASONS:
            return
        if finish_reason == "content_filter":
            raise LlmModelRefusalError
        raise LlmResponseError

    def _usage(self, usage: CompletionUsage | None) -> ModelUsage:
        if usage is None:
            return ModelUsage()
        return ModelUsage(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )

    def _legacy_max_tokens(
        self, target: LlmModelTarget, request: ModelRequest
    ) -> int | Omit:
        if target.profile.openai_dialect == OpenAICompatibleDialect.VLLM:
            return (
                request.sampling.max_tokens
                if request.sampling.max_tokens is not None
                else omit
            )
        return omit

    def _standard_max_tokens(
        self, target: LlmModelTarget, request: ModelRequest
    ) -> int | Omit:
        if target.profile.openai_dialect == OpenAICompatibleDialect.STANDARD:
            return (
                request.sampling.max_tokens
                if request.sampling.max_tokens is not None
                else omit
            )
        return omit

    def _optional_number(self, value: float | None) -> float | Omit:
        return value if value is not None else omit

    def _stream_options(
        self,
        request: ModelRequest,
    ) -> ChatCompletionStreamOptionsParam | Omit:
        if request.streaming.include_usage:
            return {"include_usage": True}
        return omit

    def _schema(self, schema: Mapping[str, JsonValue]) -> dict[str, object]:
        return {key: value for key, value in schema.items()}

    def _metadata(self, target: LlmModelTarget) -> dict[str, JsonValue]:
        return dict(routing_metadata(target))

    def _normalized_sdk_error(self, error: APIError) -> AbstractLlmError:
        if isinstance(error, APITimeoutError):
            return LlmTimeoutError()
        if isinstance(error, APIConnectionError):
            return LlmTransportError()
        if isinstance(error, APIResponseValidationError):
            return LlmResponseError()
        if isinstance(error, APIStatusError):
            if error.status_code in (408, 504):
                return LlmTimeoutError()
            if error.status_code == 429 or error.status_code >= 500:
                return LlmTransportError()
        return LlmResponseError()
