"""Tests for the native Anthropic Messages provider adapter."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from functools import partial
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic as SdkAsyncAnthropic,
    omit,
)
from anthropic.lib.streaming import MessageStreamEvent
from anthropic.types import Message, StopReason
from pydantic import SecretStr, TypeAdapter
from spakky.agent import (
    JsonObject,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)

from spakky.plugins.llm.config import LlmProfile, LlmProviderApi
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
)
from spakky.plugins.llm.provider import LlmModelTarget
from spakky.plugins.llm.providers import anthropic as provider_module
from spakky.plugins.llm.providers.anthropic import AnthropicMessagesProvider

_STREAM_EVENT_ADAPTER = TypeAdapter(MessageStreamEvent)


class _FakeMessageStream:
    """Deterministic async stream implementing the SDK helper surface used here."""

    def __init__(
        self,
        events: tuple[MessageStreamEvent, ...],
        final_message: Message,
        stream_error: APIError | None = None,
    ) -> None:
        self.events = events
        self.final_message = final_message
        self.stream_error = stream_error
        self.final_message_requested = False

    def __aiter__(self) -> AsyncIterator[MessageStreamEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[MessageStreamEvent]:
        if self.stream_error is not None:
            raise self.stream_error
        for event in self.events:
            yield event

    async def get_final_message(self) -> Message:
        self.final_message_requested = True
        return self.final_message


class _FakeMessageStreamManager:
    """Async context manager returned from mocked ``messages.stream``."""

    def __init__(
        self,
        stream: _FakeMessageStream,
        enter_error: APIError | None = None,
    ) -> None:
        self.stream = stream
        self.enter_error = enter_error
        self.closed = False

    async def __aenter__(self) -> _FakeMessageStream:
        if self.enter_error is not None:
            raise self.enter_error
        return self.stream

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.closed = True


def _target(
    *,
    api: LlmProviderApi = LlmProviderApi.ANTHROPIC_MESSAGES,
    supports_reasoning: bool = False,
    base_url: str | None = "https://anthropic.example",
) -> LlmModelTarget:
    profile_values: dict[str, object] = {
        "provider": "anthropic",
        "api": api,
        "model": "claude-profile-default",
        "base_url": base_url,
        "api_key": SecretStr("profile-secret"),
        "headers": {"x-tenant": "spakky"},
        "request_timeout_seconds": 12.0,
        "stream_timeout_seconds": 34.0,
        "max_retries": 1,
        "supports_reasoning": supports_reasoning,
    }
    if api is LlmProviderApi.ANTHROPIC_MESSAGES:
        profile_values["anthropic_max_tokens"] = 2048
    return LlmModelTarget(
        profile_name="prod-claude",
        profile=LlmProfile.model_validate(profile_values),
        model="claude-selected",
    )


def _request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Hello"),),
    )


def _message(
    content: Sequence[JsonObject] = ({"type": "text", "text": "Hello"},),
    *,
    stop_reason: StopReason | None = "end_turn",
    input_tokens: int = 3,
    output_tokens: int = 2,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
    stop_details: JsonObject | None = None,
) -> Message:
    return Message.model_validate(
        {
            "id": "msg-1",
            "content": content,
            "model": "claude-selected",
            "role": "assistant",
            "stop_reason": stop_reason,
            "stop_details": stop_details,
            "stop_sequence": None,
            "type": "message",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
        }
    )


def _event(value: JsonObject) -> MessageStreamEvent:
    return _STREAM_EVENT_ADAPTER.validate_python(value)


def _client_for_complete(
    response: Message | None = None,
    error: APIError | None = None,
) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.messages.create = AsyncMock(return_value=response, side_effect=error)
    return client


def _client_for_stream(manager: _FakeMessageStreamManager) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.messages.stream.return_value = manager
    return client


async def _collect_stream(
    target: LlmModelTarget,
    request: ModelRequest,
) -> tuple[ModelStreamEvent, ...]:
    events = [
        event async for event in AnthropicMessagesProvider().stream(target, request)
    ]
    return tuple(events)


def _sdk_request() -> httpx2.Request:
    return httpx2.Request("POST", "https://anthropic.example/v1/messages")


def _status_error(status_code: int) -> APIStatusError:
    response = httpx2.Response(status_code, request=_sdk_request())
    return APIStatusError("provider status", response=response, body={"error": {}})


def test_api_expect_anthropic_messages_family() -> None:
    """Provider registry key는 Anthropic native Messages API를 선언한다."""
    assert AnthropicMessagesProvider().api is LlmProviderApi.ANTHROPIC_MESSAGES


async def test_complete_maps_full_request_and_response_expect_native_sdk_types() -> (
    None
):
    """Complete는 system/history/tools/schema/usage를 native SDK 타입으로 매핑한다."""
    search_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "Follow policy"),
            ModelMessage(ModelMessageRole.USER, "Question"),
            ModelMessage(ModelMessageRole.EVIDENCE, "Verified evidence"),
            ModelMessage(
                ModelMessageRole.ASSISTANT,
                "I will search",
                metadata={
                    "tool_calls": (
                        {
                            "id": "history-call",
                            "name": "search",
                            "arguments": {
                                "query": "history",
                                "tags": ("docs",),
                            },
                        },
                    )
                },
            ),
            ModelMessage(
                ModelMessageRole.TOOL,
                '{"result":"history"}',
                metadata={"call_id": "history-call", "tool_name": "search"},
            ),
        ),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=output_schema),
            output_type_name="Answer",
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema=search_schema),
                    description="Search verified documents",
                ),
                ModelToolSpec(
                    name="lookup",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
        sampling=SamplingOptions(temperature=0.2, top_p=0.8, max_tokens=128),
    )
    sdk_message = _message(
        (
            {"type": "thinking", "thinking": "private", "signature": "sig"},
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "text", "text": '{"answer":"ok"}'},
            {
                "type": "tool_use",
                "id": "call-1",
                "name": "search",
                "input": {"query": "spakky", "tags": ["agent"]},
            },
        ),
        stop_reason="tool_use",
        input_tokens=3,
        output_tokens=4,
        cache_creation_input_tokens=2,
        cache_read_input_tokens=1,
    )
    client = _client_for_complete(sdk_message)

    with patch.object(
        provider_module,
        "AsyncAnthropic",
        return_value=client,
    ) as constructor:
        response = await AnthropicMessagesProvider().complete(_target(), request)

    constructor.assert_called_once_with(
        api_key="profile-secret",
        base_url="https://anthropic.example",
        webhook_key="",
        timeout=12.0,
        max_retries=1,
        default_headers={"x-tenant": "spakky"},
    )
    arguments = client.messages.create.await_args.kwargs
    assert arguments["model"] == "claude-selected"
    assert arguments["max_tokens"] == 128
    assert arguments["system"] == ({"type": "text", "text": "Follow policy"},)
    assert arguments["messages"] == (
        {"role": "user", "content": "Question"},
        {"role": "user", "content": "Verified evidence"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will search"},
                {
                    "type": "tool_use",
                    "id": "history-call",
                    "name": "search",
                    "input": {"query": "history", "tags": ["docs"]},
                },
            ],
        },
        {
            "role": "user",
            "content": (
                {
                    "type": "tool_result",
                    "tool_use_id": "history-call",
                    "content": '{"result":"history"}',
                },
            ),
        },
    )
    assert arguments["tool_choice"] == {"type": "any"}
    assert arguments["tools"] == (
        {
            "name": "search",
            "input_schema": search_schema,
            "strict": True,
            "description": "Search verified documents",
        },
        {
            "name": "lookup",
            "input_schema": {"type": "object"},
            "strict": True,
        },
    )
    assert arguments["output_config"] == {
        "format": {"type": "json_schema", "schema": output_schema}
    }
    assert arguments["extra_body"] == {"temperature": 0.2, "top_p": 0.8}
    assert response.content == '{"answer":"ok"}'
    assert response.structured_output == {"answer": "ok"}
    assert response.tool_calls[0].name == "search"
    assert response.tool_calls[0].arguments == {
        "query": "spakky",
        "tags": ("agent",),
    }
    assert response.tool_calls[0].call_id == "call-1"
    assert response.tool_calls[0].metadata == {
        "provider": "anthropic",
        "profile": "prod-claude",
        "provider_arguments": '{"query":"spakky","tags":["agent"]}',
    }
    assert response.usage.input_tokens == 6
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 10
    assert response.metadata == {
        "provider": "anthropic",
        "profile": "prod-claude",
        "finish_reason": "tool_use",
    }


async def test_complete_with_minimal_request_expect_omitted_optional_arguments() -> (
    None
):
    """Optional surface가 없으면 SDK omit sentinel과 profile token budget을 사용한다."""
    client = _client_for_complete(_message())

    with patch.object(provider_module, "AsyncAnthropic", return_value=client):
        response = await AnthropicMessagesProvider().complete(_target(), _request())

    arguments = client.messages.create.await_args.kwargs
    assert arguments["max_tokens"] == 2048
    assert arguments["messages"] == ({"role": "user", "content": "Hello"},)
    assert arguments["system"] is omit
    assert arguments["tool_choice"] is omit
    assert arguments["tools"] is omit
    assert arguments["output_config"] is omit
    assert arguments["extra_body"] is None
    assert response.usage == response.usage.__class__(
        input_tokens=3,
        output_tokens=2,
        total_tokens=5,
    )


async def test_complete_plain_assistant_history_expect_native_assistant_message() -> (
    None
):
    """Assistant history without tool_calls remains a native assistant text turn."""
    client = _client_for_complete(_message())
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.ASSISTANT, "Previous answer"),
            ModelMessage(ModelMessageRole.USER, "Continue"),
        )
    )

    with patch.object(provider_module, "AsyncAnthropic", return_value=client):
        await AnthropicMessagesProvider().complete(_target(), request)

    assert client.messages.create.await_args.kwargs["messages"] == (
        {"role": "assistant", "content": "Previous answer"},
        {"role": "user", "content": "Continue"},
    )


@pytest.mark.parametrize(
    ("choice", "expected"),
    (
        (ModelToolChoice.AUTO, {"type": "auto"}),
        (ModelToolChoice.NONE, {"type": "none"}),
    ),
)
async def test_complete_tool_choice_expect_native_anthropic_choice(
    choice: ModelToolChoice,
    expected: JsonObject,
) -> None:
    """AUTO와 NONE은 Anthropic native tool_choice object로 전달된다."""
    client = _client_for_complete(_message())
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Hello"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=choice,
        ),
    )

    with patch.object(provider_module, "AsyncAnthropic", return_value=client):
        await AnthropicMessagesProvider().complete(_target(), request)

    assert client.messages.create.await_args.kwargs["tool_choice"] == expected


async def test_provider_tool_calls_require_a_declared_catalog() -> None:
    """Complete and stream reject provider tools the caller did not authorize."""
    tool_block: JsonObject = {
        "type": "tool_use",
        "id": "call-1",
        "name": "search",
        "input": {},
    }
    complete_client = _client_for_complete(
        _message((tool_block,), stop_reason="tool_use")
    )
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=complete_client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), _request())

    start = _event(
        {"type": "content_block_start", "index": 0, "content_block": tool_block}
    )
    stream = _FakeMessageStream(
        (start,),
        _message((tool_block,), stop_reason="tool_use"),
    )
    stream_client = _client_for_stream(_FakeMessageStreamManager(stream))
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=stream_client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), _request())


async def test_required_tool_choice_rejects_zero_calls() -> None:
    """Complete and stream cannot silently weaken REQUIRED to AUTO."""
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )
    complete_client = _client_for_complete(_message())
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=complete_client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), request)

    stream = _FakeMessageStream((), _message())
    stream_client = _client_for_stream(_FakeMessageStreamManager(stream))
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=stream_client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), request)


async def test_missing_terminal_reason_rejects_complete_and_stream() -> None:
    """A provider response without a terminal reason cannot be published as success."""
    final_message = _message(stop_reason=None)
    complete_client = _client_for_complete(final_message)
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=complete_client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), _request())

    stream = _FakeMessageStream((), final_message)
    stream_client = _client_for_stream(_FakeMessageStreamManager(stream))
    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=stream_client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), _request())


async def test_complete_rejects_tool_block_without_tool_terminal_reason() -> None:
    """A validated tool block still requires Anthropic's tool_use terminal reason."""
    tool_block: JsonObject = {
        "type": "tool_use",
        "id": "call-1",
        "name": "search",
        "input": {},
    }
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            )
        ),
    )
    client = _client_for_complete(_message((tool_block,), stop_reason="end_turn"))

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), request)


async def test_stream_withholds_tool_events_until_terminal_validation() -> None:
    """A tool cannot be dispatched before the provider terminal is validated."""
    tool_block: JsonObject = {
        "type": "tool_use",
        "id": "call-1",
        "name": "search",
        "input": {},
    }
    events = (
        _event(
            {"type": "content_block_start", "index": 0, "content_block": tool_block}
        ),
        _event({"type": "content_block_stop", "index": 0, "content_block": tool_block}),
    )
    stream = _FakeMessageStream(
        events,
        _message((tool_block,), stop_reason="end_turn"),
    )
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            )
        ),
    )
    observed: list[ModelStreamEvent] = []

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        async for event in AnthropicMessagesProvider().stream(_target(), request):
            observed.append(event)

    assert observed == []


async def test_stream_validates_structured_output_before_tool_candidate() -> None:
    """Invalid structured output cannot authorize an otherwise valid tool call."""
    tool_block: JsonObject = {
        "type": "tool_use",
        "id": "call-1",
        "name": "search",
        "input": {},
    }
    stream_events = (
        _event({"type": "text", "text": '{"answer":3}', "snapshot": ""}),
        _event(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": tool_block,
            }
        ),
        _event({"type": "content_block_stop", "index": 0, "content_block": tool_block}),
    )
    stream = _FakeMessageStream(
        stream_events,
        _message(
            ({"type": "text", "text": '{"answer":3}'}, tool_block),
            stop_reason="tool_use",
        ),
    )
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                }
            )
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            )
        ),
    )
    observed: list[ModelStreamEvent] = []

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        async for event in AnthropicMessagesProvider().stream(_target(), request):
            observed.append(event)

    assert all(
        event.kind is not ModelStreamEventKind.TOOL_CALL_CANDIDATE for event in observed
    )


@pytest.mark.parametrize(
    "message",
    (
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": "invalid"},
        ),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": ("invalid",)},
        ),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": ({"id": " ", "name": "search", "arguments": {}},)},
        ),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={
                "tool_calls": ({"id": "call", "name": "search", "arguments": "{}"},)
            },
        ),
        ModelMessage(
            ModelMessageRole.TOOL,
            "result",
            metadata={"tool_name": "search"},
        ),
        ModelMessage(
            ModelMessageRole.TOOL,
            "result",
            metadata={"call_id": "call"},
        ),
    ),
)
async def test_complete_invalid_history_metadata_expect_response_error(
    message: ModelMessage,
) -> None:
    """Shared assistant/tool history convention 위반은 SDK 호출 전에 거부된다."""
    constructor = MagicMock()
    request = ModelRequest(messages=(message,))

    with (
        patch.object(provider_module, "AsyncAnthropic", constructor),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), request)

    constructor.assert_not_called()


async def test_complete_empty_tool_catalog_expect_response_error() -> None:
    """ToolCallingSpec은 Anthropic에 전달할 실제 client tool을 하나 이상 요구한다."""
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Hello"),),
        tool_calling=ToolCallingSpec(tools=()),
    )

    with pytest.raises(LlmResponseError):
        await AnthropicMessagesProvider().complete(_target(), request)


async def test_complete_none_choice_with_tool_response_expect_response_error() -> None:
    """NONE 요청에서 provider가 tool_use를 반환하면 계약 위반으로 거부된다."""
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Hello"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.NONE,
        ),
    )
    client = _client_for_complete(
        _message(
            (
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "search",
                    "input": {},
                },
            ),
            stop_reason="tool_use",
        )
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), request)


@pytest.mark.parametrize(
    ("stop_reason", "stop_details"),
    (
        ("refusal", None),
        ("end_turn", {"type": "refusal"}),
    ),
)
async def test_complete_refusal_expect_model_refusal_error(
    stop_reason: StopReason,
    stop_details: JsonObject | None,
) -> None:
    """Anthropic refusal stop reason은 generic model-refusal error로 정규화된다."""
    client = _client_for_complete(
        _message(stop_reason=stop_reason, stop_details=stop_details)
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmModelRefusalError),
    ):
        await AnthropicMessagesProvider().complete(_target(), _request())


async def test_complete_unsupported_content_block_expect_response_error() -> None:
    """Provider-only content block은 손실시키지 않고 명시적으로 거부한다."""
    client = _client_for_complete(
        _message(({"type": "container_upload", "file_id": "file-1"},))
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(_target(), _request())


async def test_complete_non_json_tool_input_expect_response_error() -> None:
    """SDK의 broad object tool input도 JSON 직렬화가 안 되면 generic response error다."""
    message = _message()
    message.content = [
        provider_module.ToolUseBlock(
            id="call-1",
            name="search",
            input={"bad": frozenset({1})},
            type="tool_use",
        )
    ]
    client = _client_for_complete(message)

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await AnthropicMessagesProvider().complete(
            _target(),
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
                tool_calling=ToolCallingSpec(
                    tools=(
                        ModelToolSpec(
                            name="search",
                            parameters=JsonSchemaConstraint(schema={"type": "object"}),
                        ),
                    )
                ),
            ),
        )


@pytest.mark.parametrize(
    ("sdk_error", "expected_error"),
    (
        (APITimeoutError(_sdk_request()), LlmTimeoutError),
        (APIConnectionError(request=_sdk_request()), LlmTransportError),
        (
            APIResponseValidationError(
                httpx2.Response(200, request=_sdk_request()),
                {"invalid": True},
            ),
            LlmResponseError,
        ),
        (_status_error(400), LlmResponseError),
        (_status_error(408), LlmTimeoutError),
        (_status_error(504), LlmTimeoutError),
        (_status_error(429), LlmTransportError),
        (_status_error(500), LlmTransportError),
        (
            APIError("generic SDK failure", _sdk_request(), body=None),
            LlmResponseError,
        ),
    ),
)
async def test_complete_sdk_failure_expect_generic_llm_error(
    sdk_error: APIError,
    expected_error: type[AbstractLlmError],
) -> None:
    """SDK timeout/connection/status/validation failures use generic LLM errors."""
    client = _client_for_complete(error=sdk_error)

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(expected_error) as raised,
    ):
        await AnthropicMessagesProvider().complete(_target(), _request())

    assert raised.value.__cause__ is sdk_error


async def test_complete_wrong_target_api_expect_provider_unavailable() -> None:
    """Anthropic provider는 allowlisted Anthropic profile 외 client를 만들지 않는다."""
    constructor = MagicMock()

    with (
        patch.object(provider_module, "AsyncAnthropic", constructor),
        pytest.raises(LlmProviderUnavailableError),
    ):
        await AnthropicMessagesProvider().complete(
            _target(api=LlmProviderApi.GOOGLE_GENERATE_CONTENT),
            _request(),
        )

    constructor.assert_not_called()


async def test_complete_missing_profile_api_key_expect_configuration_error() -> None:
    """Ambient Anthropic credentials cannot replace an allowlisted profile secret."""
    constructor = MagicMock()
    base_target = _target()
    target = replace(
        base_target,
        profile=base_target.profile.model_copy(update={"api_key": None}),
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", constructor),
        pytest.raises(LlmConfigurationError),
    ):
        await AnthropicMessagesProvider().complete(target, _request())

    constructor.assert_not_called()


async def test_stream_maps_text_reasoning_tool_structured_usage_expect_done() -> None:
    """SDK stream helper는 text/input_json/tool boundary/candidate/usage를 보존한다."""
    tool_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    tool_block = {
        "type": "tool_use",
        "id": "call-1",
        "name": "search",
        "input": {"query": "spakky"},
    }
    events = (
        _event({"type": "text", "text": '{"answer":"ok"}', "snapshot": ""}),
        _event({"type": "thinking", "thinking": "reason", "snapshot": "reason"}),
        _event(
            {"type": "content_block_start", "index": 1, "content_block": tool_block}
        ),
        _event(
            {
                "type": "input_json",
                "partial_json": '{"query":',
                "snapshot": {},
            }
        ),
        _event(
            {
                "type": "input_json",
                "partial_json": '"spakky"}',
                "snapshot": {"query": "spakky"},
            }
        ),
        _event({"type": "content_block_stop", "index": 1, "content_block": tool_block}),
    )
    final_message = _message(
        (
            {"type": "text", "text": '{"answer":"ok"}'},
            tool_block,
        ),
        stop_reason="tool_use",
        input_tokens=5,
        output_tokens=6,
    )
    stream = _FakeMessageStream(events, final_message)
    manager = _FakeMessageStreamManager(stream)
    client = _client_for_stream(manager)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=output_schema)
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema=tool_schema),
                ),
            )
        ),
        sampling=SamplingOptions(max_tokens=64),
    )

    with patch.object(
        provider_module,
        "AsyncAnthropic",
        return_value=client,
    ) as constructor:
        mapped = [
            event
            async for event in AnthropicMessagesProvider().stream(
                _target(supports_reasoning=True),
                request,
            )
        ]

    constructor.assert_called_once_with(
        api_key="profile-secret",
        base_url="https://anthropic.example",
        webhook_key="",
        timeout=34.0,
        max_retries=1,
        default_headers={"x-tenant": "spakky"},
    )
    assert [event.kind for event in mapped] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.REASONING_DELTA,
        ModelStreamEventKind.TOOL_CALL_START,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_END,
        ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        ModelStreamEventKind.STRUCTURED_OUTPUT,
        ModelStreamEventKind.DONE,
    ]
    assert mapped[0].token_delta == '{"answer":"ok"}'
    assert mapped[1].reasoning_delta == "reason"
    assert mapped[2].tool_call is mapped[3].tool_call
    assert mapped[2].tool_call is mapped[5].tool_call
    assert mapped[3].tool_call_args_delta == '{"query":'
    assert mapped[4].tool_call_args_delta == '"spakky"}'
    assert mapped[6].tool_call is not None
    assert mapped[6].tool_call.arguments == {"query": "spakky"}
    assert mapped[6].tool_call.metadata["provider_arguments"] == ('{"query":"spakky"}')
    assert mapped[7].structured_output == {"answer": "ok"}
    assert mapped[8].usage is not None
    assert mapped[8].usage.total_tokens == 11
    assert mapped[8].metadata == {
        "provider": "anthropic",
        "profile": "prod-claude",
        "finish_reason": "tool_use",
    }
    assert all(event.metadata.get("provider") == "anthropic" for event in mapped)
    assert stream.final_message_requested is True
    assert manager.closed is True


async def test_anthropic_profile_fences_ambient_sdk_connection(
    monkeypatch,
) -> None:
    """Ambient Anthropic routing cannot replace the official profile endpoint."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ambient.invalid")
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(provider_module, "AsyncAnthropic", SdkAsyncAnthropic)

    client = AnthropicMessagesProvider()._client(
        _target(base_url=None),
        timeout_seconds=12.0,
    )
    try:
        assert str(client.base_url) == "https://api.anthropic.com"
    finally:
        await client.close()


@pytest.mark.parametrize(
    ("operation", "headers", "body"),
    [
        ("complete", {"content-type": "application/json"}, b"not-json"),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant","stop_reason":"end_turn",'
            b'"stop_sequence":null,"type":"message","usage":"invalid"}',
        ),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant",'
            b'"stop_reason":"future_reason","stop_sequence":null,'
            b'"type":"message","usage":{"input_tokens":1,"output_tokens":1}}',
        ),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant","stop_reason":"pause_turn",'
            b'"stop_sequence":null,"type":"message",'
            b'"usage":{"input_tokens":1,"output_tokens":1}}',
        ),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b"event: message_start\ndata: not-json\n\n",
        ),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b'event: message_start\ndata: {"type":"message_start","message":'
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant","stop_reason":"end_turn",'
            b'"stop_sequence":null,"type":"message","usage":"invalid"}}\n\n',
        ),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b'event: message_start\ndata: {"type":"message_start","message":'
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant",'
            b'"stop_reason":"future_reason","stop_sequence":null,'
            b'"type":"message","usage":{"input_tokens":1,'
            b'"output_tokens":1}}}\n\n',
        ),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b'event: message_start\ndata: {"type":"message_start","message":'
            b'{"id":"msg-1","content":[{"type":"text","text":"ok"}],'
            b'"model":"claude","role":"assistant","stop_reason":"pause_turn",'
            b'"stop_sequence":null,"type":"message",'
            b'"usage":{"input_tokens":1,"output_tokens":1}}}\n\n',
        ),
    ],
)
async def test_installed_anthropic_sdk_rejects_malformed_success_payloads(
    monkeypatch,
    operation: str,
    headers: dict[str, str],
    body: bytes,
) -> None:
    """Installed-SDK decode and typed-body defects stay generic response errors."""

    async def malformed_response(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=headers, content=body, request=request)

    transport = httpx2.MockTransport(malformed_response)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        monkeypatch.setattr(
            provider_module,
            "AsyncAnthropic",
            partial(SdkAsyncAnthropic, http_client=http_client),
        )
        provider = AnthropicMessagesProvider()

        with pytest.raises(LlmResponseError):
            if operation == "complete":
                await provider.complete(_target(), _request())
            else:
                await _collect_stream(_target(), _request())


def test_anthropic_profile_rejects_ambient_custom_headers(monkeypatch) -> None:
    """Ambient SDK headers cannot extend the profile header allowlist."""
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Ambient: injected")

    with pytest.raises(LlmConfigurationError):
        AnthropicMessagesProvider()._client(_target(), timeout_seconds=12.0)


async def test_stream_disabled_reasoning_and_usage_expect_done_without_optional_data() -> (
    None
):
    """Profile reasoning과 request usage opt-out은 해당 stream payload를 생략한다."""
    stream = _FakeMessageStream(
        (
            _event({"type": "text", "text": "visible", "snapshot": "visible"}),
            _event(
                {
                    "type": "thinking",
                    "thinking": "hidden",
                    "snapshot": "hidden",
                }
            ),
            _event(
                {
                    "type": "content_block_stop",
                    "index": 0,
                    "content_block": {"type": "text", "text": "visible"},
                }
            ),
        ),
        _message(),
    )
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        streaming=StreamingOptions(include_usage=False),
    )

    with patch.object(provider_module, "AsyncAnthropic", return_value=client):
        mapped = [
            event
            async for event in AnthropicMessagesProvider().stream(_target(), request)
        ]

    assert [event.kind for event in mapped] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.DONE,
    ]
    assert mapped[0].token_delta == "visible"
    assert mapped[1].usage is None


def test_tool_stream_invariant_failures_expect_response_error() -> None:
    """Impossible internal state loss and changed tool identity still fail closed."""
    provider = AnthropicMessagesProvider()
    block = provider_module.ToolUseBlock(
        id="call",
        name="search",
        input={},
        type="tool_use",
    )
    handle = ModelToolCall(name="search", arguments={}, call_id="other")

    with pytest.raises(LlmResponseError):
        provider._active_tool_state(0, {})
    with pytest.raises(LlmResponseError):
        provider._stopped_tool_state(0, 0, {}, block)
    with pytest.raises(LlmResponseError):
        provider._stopped_tool_state(
            0,
            0,
            {0: provider_module._ToolStreamState(handle)},
            block,
        )


@pytest.mark.parametrize(
    "events",
    (
        (
            _event(
                {
                    "type": "input_json",
                    "partial_json": "{}",
                    "snapshot": {},
                }
            ),
        ),
        (
            _event(
                {
                    "type": "content_block_stop",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call",
                        "name": "search",
                        "input": {},
                    },
                }
            ),
        ),
        (
            _event(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call",
                        "name": "search",
                        "input": {},
                    },
                }
            ),
        ),
        (
            _event(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call",
                        "name": "search",
                        "input": {},
                    },
                }
            ),
            _event(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call-2",
                        "name": "search",
                        "input": {},
                    },
                }
            ),
        ),
    ),
)
async def test_stream_invalid_tool_framing_expect_response_error(
    events: tuple[MessageStreamEvent, ...],
) -> None:
    """Orphan, missing, unclosed, duplicate tool frames raise for one terminalizer."""
    stream = _FakeMessageStream(events, _message())
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            )
        ),
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), request)


async def test_stream_none_tool_choice_expect_response_error() -> None:
    """NONE tool choice에서 tool start가 오면 generic response error를 던진다."""
    start = _event(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "call",
                "name": "search",
                "input": {},
            },
        }
    )
    stream = _FakeMessageStream((start,), _message())
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.NONE,
        ),
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), request)


async def test_stream_refusal_expect_model_refusal_error() -> None:
    """Final Anthropic refusal은 상위 single terminalizer에 generic error로 전달된다."""
    stream = _FakeMessageStream((), _message(stop_reason="refusal"))
    client = _client_for_stream(_FakeMessageStreamManager(stream))

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmModelRefusalError),
    ):
        await _collect_stream(_target(), _request())


async def test_stream_sdk_timeout_expect_normalized_error() -> None:
    """Stream context/iteration SDK timeout도 generic exception으로 정규화된다."""
    sdk_error = APITimeoutError(_sdk_request())
    stream = _FakeMessageStream((), _message())
    manager = _FakeMessageStreamManager(stream, enter_error=sdk_error)
    client = _client_for_stream(manager)

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmTimeoutError) as raised,
    ):
        await _collect_stream(_target(), _request())

    assert raised.value.__cause__ is sdk_error


async def test_stream_invalid_structured_output_expect_response_error() -> None:
    """Streamed structured JSON의 terminal schema 검증 실패를 그대로 전달한다."""
    stream = _FakeMessageStream(
        (_event({"type": "text", "text": "{}", "snapshot": "{}"}),),
        _message(({"type": "text", "text": "{}"},)),
    )
    client = _client_for_stream(_FakeMessageStreamManager(stream))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "Question"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                }
            )
        ),
    )

    with (
        patch.object(provider_module, "AsyncAnthropic", return_value=client),
        pytest.raises(LlmResponseError),
    ):
        await _collect_stream(_target(), request)


async def test_stream_wrong_target_api_expect_provider_unavailable() -> None:
    """Stream도 non-Anthropic allowlisted profile에 SDK client를 만들지 않는다."""
    constructor = MagicMock()

    with (
        patch.object(provider_module, "AsyncAnthropic", constructor),
        pytest.raises(LlmProviderUnavailableError),
    ):
        await _collect_stream(
            _target(api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            _request(),
        )

    constructor.assert_not_called()
