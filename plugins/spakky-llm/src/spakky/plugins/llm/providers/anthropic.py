"""Anthropic Messages adapter backed by the official async Python SDK."""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError, dumps
from os import environ
from typing import override

from anthropic import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    Omit,
    omit,
)
from anthropic.types import (
    JSONOutputFormatParam,
    Message,
    MessageParam,
    OutputConfigParam,
    RedactedThinkingBlock,
    TextBlock,
    TextBlockParam,
    ThinkingBlock,
    ToolChoiceParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
    ToolUseBlockParam,
    Usage,
)
from spakky.agent import (
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
from spakky.plugins.llm.config import LlmProviderApi
from spakky.plugins.llm.constants import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    OFFICIAL_ANTHROPIC_BASE_URL,
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
)
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    ensure_terminal_tool_choice,
    ensure_tool_call_allowed,
    routing_metadata,
)

type _AnthropicHistoryBlock = TextBlockParam | ToolUseBlockParam | ToolResultBlockParam
_SUCCESS_STOP_REASONS = frozenset(
    {
        "end_turn",
        "max_tokens",
        "stop_sequence",
        "tool_use",
        "model_context_window_exceeded",
    }
)


@dataclass(slots=True)
class _ToolStreamState:
    """Accumulate one SDK-framed client-tool call without executing it."""

    handle: ModelToolCall
    argument_fragments: list[str] = field(default_factory=list)


@Pod()
class AnthropicMessagesProvider(ILLMProvider):
    """Translate Spakky model contracts to Anthropic's native Messages API."""

    __codec: LlmJsonCodec

    def __init__(self) -> None:
        self.__codec = LlmJsonCodec()

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        """Return the native Anthropic Messages API family."""
        return frozenset({LlmProviderApi.ANTHROPIC_MESSAGES})

    @property
    @override
    def is_default(self) -> bool:
        """Mark the first-party Anthropic adapter as replaceable default."""
        return True

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        """Return one provider-neutral completion through ``AsyncAnthropic``."""
        messages, system = self._history(request)
        constraints = self.__codec.tool_constraints(request.tool_calling)
        try:
            async with self._client(
                target,
                target.profile.request_timeout_seconds,
            ) as client:
                response = await client.messages.create(
                    max_tokens=self._max_tokens(target, request),
                    messages=messages,
                    model=target.model,
                    output_config=self._output_config(request),
                    system=system,
                    tool_choice=self._tool_choice(request),
                    tools=self._tools(request),
                    extra_body=self._sampling_body(request),
                )
        except APIError as sdk_error:
            raise self._provider_error(sdk_error) from sdk_error
        except JSONDecodeError as sdk_error:
            raise LlmResponseError from sdk_error
        try:
            return self._response(target, request, response, constraints)
        except (AttributeError, TypeError) as sdk_error:
            raise LlmResponseError from sdk_error

    def _response(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        response: Message,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelResponse:
        """Validate and map one SDK-decoded Anthropic message."""
        self._ensure_not_refused(response)
        tool_calls = tuple(
            self._tool_call(block, target, constraints)
            for block in response.content
            if isinstance(block, ToolUseBlock)
        )
        if response.stop_reason is None:
            raise LlmResponseError
        if (len(tool_calls) > 0) != (response.stop_reason == "tool_use"):
            raise LlmResponseError
        ensure_terminal_tool_choice(request, len(tool_calls))
        content = self._text_content(response)
        structured_output: JsonValue = None
        if request.structured_output is not None:
            structured_output = self.__codec.decode_value(
                content,
                request.structured_output.constraint,
            )
        return ModelResponse(
            content=content,
            structured_output=structured_output,
            tool_calls=tool_calls,
            usage=self._usage(response.usage),
            metadata={
                **self._metadata(target),
                "finish_reason": response.stop_reason,
            },
        )

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Return SDK-managed message, tool, usage, and terminal events."""
        return self._stream(target, request)

    async def _stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        finish_reason: str | None = None
        usage: ModelUsage | None = None
        completed_tool_count = 0
        pending_tool_events: list[ModelStreamEvent] = []
        try:
            messages, system = self._history(request)
            constraints = self.__codec.tool_constraints(request.tool_calling)
            structured_fragments: list[str] = []
            tool_states: dict[int, _ToolStreamState] = {}
            active_tool_index: int | None = None

            async with self._client(
                target,
                target.profile.stream_timeout_seconds,
            ) as client:
                async with client.messages.stream(
                    max_tokens=self._max_tokens(target, request),
                    messages=messages,
                    model=target.model,
                    output_config=self._output_config(request),
                    system=system,
                    tool_choice=self._tool_choice(request),
                    tools=self._tools(request),
                    extra_body=self._sampling_body(request),
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            if request.structured_output is not None:
                                structured_fragments.append(event.text)
                            yield ModelStreamEvent(
                                kind=ModelStreamEventKind.TOKEN_DELTA,
                                token_delta=event.text,
                                metadata=self._metadata(target),
                            )
                        elif event.type == "thinking":
                            if target.route.capability.supports_reasoning:
                                yield ModelStreamEvent(
                                    kind=ModelStreamEventKind.REASONING_DELTA,
                                    reasoning_delta=event.thinking,
                                    metadata=self._metadata(target),
                                )
                        elif event.type == "content_block_start" and isinstance(
                            event.content_block,
                            ToolUseBlock,
                        ):
                            self._ensure_tool_stream_start(
                                event.index,
                                tool_states,
                                request,
                            )
                            active_tool_index = event.index
                            handle = ModelToolCall(
                                name=event.content_block.name,
                                arguments={},
                                call_id=event.content_block.id,
                                metadata=self._metadata(target),
                            )
                            tool_states[event.index] = _ToolStreamState(handle)
                            pending_tool_events.append(
                                ModelStreamEvent(
                                    kind=ModelStreamEventKind.TOOL_CALL_START,
                                    tool_call=handle,
                                    metadata=self._metadata(target),
                                )
                            )
                        elif event.type == "input_json":
                            state = self._active_tool_state(
                                active_tool_index,
                                tool_states,
                            )
                            state.argument_fragments.append(event.partial_json)
                            pending_tool_events.append(
                                ModelStreamEvent(
                                    kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
                                    tool_call=state.handle,
                                    tool_call_args_delta=event.partial_json,
                                    metadata=self._metadata(target),
                                )
                            )
                        elif event.type == "content_block_stop" and isinstance(
                            event.content_block,
                            ToolUseBlock,
                        ):
                            state = self._stopped_tool_state(
                                event.index,
                                active_tool_index,
                                tool_states,
                                event.content_block,
                            )
                            candidate = self._tool_call(
                                event.content_block,
                                target,
                                constraints,
                                provider_arguments="".join(state.argument_fragments),
                            )
                            pending_tool_events.append(
                                ModelStreamEvent(
                                    kind=ModelStreamEventKind.TOOL_CALL_END,
                                    tool_call=state.handle,
                                    metadata=self._metadata(target),
                                )
                            )
                            pending_tool_events.append(
                                ModelStreamEvent(
                                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                                    tool_call=candidate,
                                    metadata=self._metadata(target),
                                )
                            )
                            completed_tool_count += 1
                            active_tool_index = None
                    final_message = await stream.get_final_message()

            if len(tool_states) > 0 or active_tool_index is not None:
                raise LlmResponseError
            self._ensure_not_refused(final_message)
            finish_reason = final_message.stop_reason
            if finish_reason is None:
                raise LlmResponseError
            if (completed_tool_count > 0) != (finish_reason == "tool_use"):
                raise LlmResponseError
            ensure_terminal_tool_choice(request, completed_tool_count)
            if request.streaming.include_usage:
                usage = self._usage(final_message.usage)
            structured_output: JsonValue = None
            if request.structured_output is not None:
                structured_output = self.__codec.decode_value(
                    "".join(structured_fragments),
                    request.structured_output.constraint,
                )
            for pending_tool_event in pending_tool_events:
                yield pending_tool_event
            if request.structured_output is not None:
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output=structured_output,
                    metadata=self._metadata(target),
                )
        except APIError as sdk_error:
            raise self._provider_error(sdk_error) from sdk_error
        except (JSONDecodeError, AttributeError, TypeError) as sdk_error:
            raise LlmResponseError from sdk_error
        yield done_event(target, finish_reason, usage)

    def _client(
        self,
        target: LlmModelTarget,
        timeout_seconds: float,
    ) -> AsyncAnthropic:
        profile = target.profile
        if profile.api not in self.apis:
            raise LlmProviderUnavailableError
        if "ANTHROPIC_CUSTOM_HEADERS" in environ:
            raise LlmConfigurationError
        api_key = profile.api_key_value()
        if api_key is None:
            raise LlmConfigurationError
        return AsyncAnthropic(
            api_key=api_key,
            base_url=profile.base_url or OFFICIAL_ANTHROPIC_BASE_URL,
            webhook_key="",
            timeout=timeout_seconds,
            max_retries=profile.max_retries,
            default_headers=dict(profile.headers),
        )

    def _history(
        self,
        request: ModelRequest,
    ) -> tuple[tuple[MessageParam, ...], tuple[TextBlockParam, ...] | Omit]:
        messages: list[MessageParam] = []
        system: list[TextBlockParam] = []
        for message in request.assemble_messages():
            if message.role is ModelMessageRole.SYSTEM:
                system.append({"type": "text", "text": message.content})
                continue
            if message.role in (ModelMessageRole.USER, ModelMessageRole.EVIDENCE):
                messages.append({"role": "user", "content": message.content})
                continue
            if message.role is ModelMessageRole.ASSISTANT:
                messages.append(self._assistant_message(message))
                continue
            messages.append(self._tool_result_message(message))
        return tuple(messages), tuple(system) if len(system) > 0 else omit

    def _assistant_message(self, message: ModelMessage) -> MessageParam:
        raw_tool_calls = message.metadata.get("tool_calls")
        if raw_tool_calls is None:
            return {"role": "assistant", "content": message.content}
        if not isinstance(raw_tool_calls, Sequence) or isinstance(raw_tool_calls, str):
            raise LlmResponseError
        blocks: list[_AnthropicHistoryBlock] = []
        if message.content != "":
            blocks.append({"type": "text", "text": message.content})
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, Mapping):
                raise LlmResponseError
            call_id = self._required_text(raw_tool_call, "id")
            name = self._required_text(raw_tool_call, "name")
            arguments = raw_tool_call.get("arguments")
            if not isinstance(arguments, Mapping):
                raise LlmResponseError
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": self._sdk_json_object(arguments),
                }
            )
        return {
            "role": "assistant",
            "content": blocks if len(blocks) > 0 else message.content,
        }

    def _tool_result_message(self, message: ModelMessage) -> MessageParam:
        call_id = self._required_text(message.metadata, "call_id")
        self._required_text(message.metadata, "tool_name")
        result: ToolResultBlockParam = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": message.content,
        }
        return {"role": "user", "content": (result,)}

    def _required_text(
        self,
        values: Mapping[str, JsonValue],
        key: str,
    ) -> str:
        value = values.get(key)
        if not isinstance(value, str) or value.strip() == "":
            raise LlmResponseError
        return value

    def _tools(self, request: ModelRequest) -> tuple[ToolParam, ...] | Omit:
        if request.tool_calling is None:
            return omit
        if len(request.tool_calling.tools) == 0:
            raise LlmResponseError
        tools: list[ToolParam] = []
        for tool in request.tool_calling.tools:
            item: ToolParam = {
                "name": tool.name,
                "input_schema": self._sdk_json_object(tool.parameters.schema),
                "strict": tool.parameters.strict,
            }
            if tool.description is not None:
                item["description"] = tool.description
            tools.append(item)
        return tuple(tools)

    def _tool_choice(self, request: ModelRequest) -> ToolChoiceParam | Omit:
        if request.tool_calling is None:
            return omit
        if request.tool_calling.choice is ModelToolChoice.AUTO:
            return {"type": "auto"}
        if request.tool_calling.choice is ModelToolChoice.NONE:
            return {"type": "none"}
        return {"type": "any"}

    def _output_config(self, request: ModelRequest) -> OutputConfigParam | Omit:
        if request.structured_output is None:
            return omit
        output_format: JSONOutputFormatParam = {
            "type": "json_schema",
            "schema": self._sdk_json_object(
                request.structured_output.constraint.schema
            ),
        }
        return {"format": output_format}

    def _sampling_body(self, request: ModelRequest) -> dict[str, float] | None:
        body: dict[str, float] = {}
        if request.sampling.temperature is not None:
            body["temperature"] = request.sampling.temperature
        if request.sampling.top_p is not None:
            body["top_p"] = request.sampling.top_p
        return body if len(body) > 0 else None

    def _max_tokens(self, target: LlmModelTarget, request: ModelRequest) -> int:
        if request.sampling.max_tokens is not None:
            return request.sampling.max_tokens
        return DEFAULT_ANTHROPIC_MAX_TOKENS

    def _text_content(self, message: Message) -> str:
        fragments: list[str] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                fragments.append(block.text)
            elif isinstance(
                block,
                ToolUseBlock | ThinkingBlock | RedactedThinkingBlock,
            ):
                continue
            else:
                raise LlmResponseError
        return "".join(fragments)

    def _tool_call(
        self,
        block: ToolUseBlock,
        target: LlmModelTarget,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
        provider_arguments: str | None = None,
    ) -> ModelToolCall:
        constraint = self.__codec.tool_constraint(block.name, constraints)
        serialized = (
            provider_arguments
            if provider_arguments is not None
            else self._serialize_tool_input(block.input)
        )
        return ModelToolCall(
            name=block.name,
            arguments=self.__codec.decode_object(
                self._serialize_tool_input(block.input),
                constraint,
            ),
            call_id=block.id,
            metadata={
                **self._metadata(target),
                "provider_arguments": serialized,
            },
        )

    def _serialize_tool_input(self, value: Mapping[str, object]) -> str:
        """Serialize the SDK's deliberately broad tool-input response type."""
        try:
            return dumps(value, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise LlmResponseError from error

    def _usage(self, usage: Usage) -> ModelUsage:
        cache_write_5m_input_tokens: int | None = None
        cache_write_1h_input_tokens: int | None = None
        if (
            usage.cache_creation_input_tokens is not None
            and usage.cache_creation_input_tokens > 0
            and usage.cache_creation is None
        ):
            raise LlmResponseError
        if usage.cache_creation is not None:
            cache_write_5m_input_tokens = usage.cache_creation.ephemeral_5m_input_tokens
            cache_write_1h_input_tokens = usage.cache_creation.ephemeral_1h_input_tokens
            if cache_write_5m_input_tokens + cache_write_1h_input_tokens != (
                usage.cache_creation_input_tokens or 0
            ):
                raise LlmResponseError
        input_tokens = (
            usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0)
        )
        return ModelUsage(
            input_tokens=input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=input_tokens + usage.output_tokens,
            cached_input_tokens=usage.cache_read_input_tokens,
            cache_write_input_tokens=usage.cache_creation_input_tokens,
            cache_write_5m_input_tokens=cache_write_5m_input_tokens,
            cache_write_1h_input_tokens=cache_write_1h_input_tokens,
        )

    def _ensure_not_refused(self, message: Message) -> None:
        if message.stop_reason == "refusal" or message.stop_details is not None:
            raise LlmModelRefusalError
        if (
            message.stop_reason is not None
            and message.stop_reason not in _SUCCESS_STOP_REASONS
        ):
            raise LlmResponseError

    def _ensure_tool_stream_start(
        self,
        index: int,
        tool_states: Mapping[int, _ToolStreamState],
        request: ModelRequest,
    ) -> None:
        if index in tool_states:
            raise LlmResponseError
        ensure_tool_call_allowed(request)

    def _active_tool_state(
        self,
        active_tool_index: int | None,
        tool_states: Mapping[int, _ToolStreamState],
    ) -> _ToolStreamState:
        if active_tool_index is None:
            raise LlmResponseError
        state = tool_states.get(active_tool_index)
        if state is None:
            raise LlmResponseError
        return state

    def _stopped_tool_state(
        self,
        index: int,
        active_tool_index: int | None,
        tool_states: dict[int, _ToolStreamState],
        block: ToolUseBlock,
    ) -> _ToolStreamState:
        if active_tool_index != index:
            raise LlmResponseError
        state = tool_states.pop(index, None)
        if state is None:
            raise LlmResponseError
        if state.handle.call_id != block.id or state.handle.name != block.name:
            raise LlmResponseError
        return state

    def _provider_error(self, error: APIError) -> AbstractLlmError:
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
        return LlmResponseError()

    def _metadata(self, target: LlmModelTarget) -> dict[str, JsonValue]:
        return dict(routing_metadata(target))

    def _sdk_json_object(
        self,
        value: Mapping[str, JsonValue],
    ) -> dict[str, object]:
        """Widen portable JSON only at Anthropic's generated SDK boundary."""
        return {key: self._sdk_json_value(item) for key, item in value.items()}

    def _sdk_json_value(self, value: JsonValue) -> object:
        """Match the SDK's ``dict[str, object]`` JSON schema annotation."""
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Mapping):
            return self._sdk_json_object(value)
        return [self._sdk_json_value(item) for item in value]
