"""Unit tests for the official OpenAI chat-completions provider."""

from collections.abc import AsyncIterator
from functools import partial
from types import TracebackType

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI as SdkAsyncOpenAI,
    omit,
)
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic import SecretStr
from pytest import MonkeyPatch
from spakky.agent import (
    JsonSchemaConstraint,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelCapability,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)

from spakky.plugins.llm.config import (
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import (
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.provider import LlmModelTarget
from spakky.plugins.llm.providers import openai as openai_module
from spakky.plugins.llm.providers.openai import OpenAIChatProvider


class _FakeAsyncStream:
    def __init__(
        self,
        chunks: tuple[ChatCompletionChunk, ...],
        error: BaseException | None,
    ) -> None:
        self._chunks = chunks
        self._error = error
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "_FakeAsyncStream":
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_value, traceback)
        self.exited = True

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[ChatCompletionChunk]:
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error


class _FakeCompletions:
    calls: list[dict[str, object]] = []
    completion: ChatCompletion | None = None
    chunks: tuple[ChatCompletionChunk, ...] = ()
    error: BaseException | None = None
    stream_error: BaseException | None = None
    stream: _FakeAsyncStream | None = None

    async def create(
        self,
        **kwargs: object,
    ) -> ChatCompletion | _FakeAsyncStream:
        type(self).calls.append(kwargs)
        error = type(self).error
        if error is not None:
            raise error
        if kwargs.get("stream") is True:
            stream = _FakeAsyncStream(type(self).chunks, type(self).stream_error)
            type(self).stream = stream
            return stream
        completion = type(self).completion
        if completion is None:
            raise AssertionError("fake completion was not configured")
        return completion


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeAsyncOpenAI:
    init_calls: list[dict[str, object]] = []
    entered = False
    exited = False

    def __init__(self, **kwargs: object) -> None:
        type(self).init_calls.append(kwargs)
        self.chat = _FakeChat()

    async def __aenter__(self) -> "_FakeAsyncOpenAI":
        type(self).entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_value, traceback)
        type(self).exited = True


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch: MonkeyPatch) -> None:
    _FakeCompletions.calls = []
    _FakeCompletions.completion = None
    _FakeCompletions.chunks = ()
    _FakeCompletions.error = None
    _FakeCompletions.stream_error = None
    _FakeCompletions.stream = None
    _FakeAsyncOpenAI.init_calls = []
    _FakeAsyncOpenAI.entered = False
    _FakeAsyncOpenAI.exited = False
    monkeypatch.setattr(openai_module, "AsyncOpenAI", _FakeAsyncOpenAI)


def _schema() -> dict[str, JsonValue]:
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    return schema


def _foreign_target() -> LlmModelTarget:
    return LlmModelTarget(
        model_ref="support/foreign",
        profile_name="foreign",
        profile=LlmProfile.model_construct(
            provider="anthropic",
            api=LlmProviderApi.ANTHROPIC_MESSAGES,
            openai_dialect=OpenAICompatibleDialect.STANDARD,
        ),
        route=LlmModelRoute(profile="foreign", model="claude"),
    )


def _tool_spec() -> ModelToolSpec:
    return ModelToolSpec(
        name="lookup_weather",
        description="Look up weather",
        parameters=JsonSchemaConstraint(
            schema={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            }
        ),
    )


def _target(
    *,
    dialect: OpenAICompatibleDialect = OpenAICompatibleDialect.VLLM,
    api: LlmProviderApi = LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
    api_key: SecretStr | None = SecretStr("secret"),
    base_url: str | None = "http://localhost:8000/v1",
    supports_reasoning: bool = False,
    include_vllm_extensions: bool = True,
) -> LlmModelTarget:
    return LlmModelTarget(
        model_ref="support/primary",
        profile_name="vllm-local",
        profile=LlmProfile(
            provider="openai",
            api=api,
            api_key=api_key,
            base_url=base_url,
            openai_dialect=dialect,
            request_timeout_seconds=11,
            stream_timeout_seconds=22,
            max_retries=3,
            headers={"X-Tenant": "tenant-a"},
        ),
        route=LlmModelRoute(
            profile="vllm-local",
            model="selected-model",
            capability=ModelCapability(supports_reasoning=supports_reasoning),
            chat_template_kwargs=(
                {"enable_thinking": True}
                if dialect == OpenAICompatibleDialect.VLLM and include_vllm_extensions
                else {}
            ),
        ),
    )


def _completion(
    *,
    content: str | None = "ok",
    finish_reason: str = "stop",
    refusal: str | None = None,
    tool_calls: list[dict[str, object]] | None = None,
    extra_message: dict[str, object] | None = None,
) -> ChatCompletion:
    message: dict[str, object] = {
        "role": "assistant",
        "content": content,
        "refusal": refusal,
    }
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if extra_message is not None:
        message.update(extra_message)
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-1",
            "created": 1,
            "model": "served-model",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": message,
                }
            ],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "total_tokens": 7,
            },
        }
    )


def _chunk(
    *,
    delta: dict[str, object] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
) -> ChatCompletionChunk:
    choices: list[dict[str, object]] = []
    if delta is not None or finish_reason is not None:
        choices.append(
            {
                "index": 0,
                "delta": delta or {},
                "finish_reason": finish_reason,
            }
        )
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-stream",
            "created": 1,
            "model": "served-model",
            "object": "chat.completion.chunk",
            "choices": choices,
            "usage": usage,
        }
    )


async def test_complete_maps_allowlisted_vllm_profile_and_structured_request() -> None:
    """vLLM profile uses only profile credentials and emits its dialect extras."""
    _FakeCompletions.completion = _completion(content='{"answer":"ok"}')
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "system"),
            ModelMessage(ModelMessageRole.USER, "question"),
            ModelMessage(
                ModelMessageRole.ASSISTANT,
                "",
                metadata={
                    "tool_calls": (
                        {
                            "id": "call-old",
                            "name": "lookup_weather",
                            "arguments": {"city": "Seoul"},
                        },
                    )
                },
            ),
            ModelMessage(
                ModelMessageRole.TOOL,
                "sunny",
                metadata={"call_id": "call-old", "tool_name": "lookup_weather"},
            ),
            ModelMessage(ModelMessageRole.EVIDENCE, "trusted evidence"),
        ),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=_schema()),
            output_type_name="Answer",
        ),
        tool_calling=ToolCallingSpec(
            tools=(_tool_spec(),),
            choice=ModelToolChoice.AUTO,
        ),
        sampling=SamplingOptions(temperature=0.2, top_p=0.8, max_tokens=64),
    )

    response = await OpenAIChatProvider().complete(_target(), request)

    assert response.content == '{"answer":"ok"}'
    assert response.structured_output == {"answer": "ok"}
    assert response.usage.input_tokens == 3
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 7
    assert response.metadata == {
        "model_ref": "support/primary",
        "provider": "openai",
        "profile": "vllm-local",
        "finish_reason": "stop",
        "response_id": "chatcmpl-1",
        "model": "selected-model",
        "response_model": "served-model",
    }
    assert _FakeAsyncOpenAI.init_calls == [
        {
            "api_key": "secret",
            "admin_api_key": "",
            "base_url": "http://localhost:8000/v1",
            "organization": "",
            "project": "",
            "webhook_secret": "",
            "timeout": 11.0,
            "max_retries": 3,
            "default_headers": {"X-Tenant": "tenant-a"},
        }
    ]
    call = _FakeCompletions.calls[0]
    assert call["model"] == "selected-model"
    assert call["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-old",
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "arguments": '{"city":"Seoul"}',
                    },
                }
            ],
        },
        {"role": "tool", "content": "sunny", "tool_call_id": "call-old"},
        {"role": "user", "content": "trusted evidence"},
    ]
    assert call["temperature"] == 0.2
    assert call["top_p"] == 0.8
    assert call["max_tokens"] == 64
    assert call["max_completion_tokens"] is omit
    assert call["tool_choice"] == "auto"
    assert call["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Look up weather",
                "parameters": _tool_spec().parameters.schema,
                "strict": True,
            },
        }
    ]
    assert call["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "Answer",
            "schema": _schema(),
            "strict": True,
        },
    }
    assert call["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
        "structured_outputs": {"json": _schema()},
    }
    assert _FakeAsyncOpenAI.entered is True
    assert _FakeAsyncOpenAI.exited is True


async def test_complete_standard_dialect_maps_max_completion_tokens_and_reasoning() -> (
    None
):
    """Standard OpenAI requests avoid vLLM extras and preserve returned reasoning."""
    _FakeCompletions.completion = _completion(
        content="answer",
        extra_message={"reasoning_content": "summary"},
    )
    target = _target(
        dialect=OpenAICompatibleDialect.STANDARD,
        base_url=None,
        supports_reasoning=True,
    )

    response = await OpenAIChatProvider().complete(
        target,
        ModelRequest(
            messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
            sampling=SamplingOptions(max_tokens=32),
        ),
    )

    call = _FakeCompletions.calls[0]
    assert call["max_tokens"] is omit
    assert call["max_completion_tokens"] == 32
    assert call["tools"] is omit
    assert call["response_format"] is omit
    assert call["extra_body"] is None
    assert response.metadata["reasoning"] == "summary"


async def test_complete_maps_function_tool_call_without_executing_it() -> None:
    """Provider tool calls become validated candidates and are never executed."""
    _FakeCompletions.completion = _completion(
        content=None,
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "lookup_weather",
                    "arguments": '{"city":"Seoul"}',
                },
            }
        ],
    )

    response = await OpenAIChatProvider().complete(
        _target(),
        ModelRequest(
            messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
            tool_calling=ToolCallingSpec(tools=(_tool_spec(),)),
        ),
    )

    assert response.content == ""
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "lookup_weather"
    assert response.tool_calls[0].arguments == {"city": "Seoul"}
    assert response.tool_calls[0].call_id == "call-1"
    assert response.tool_calls[0].metadata == {
        "model_ref": "support/primary",
        "provider": "openai",
        "profile": "vllm-local",
        "model": "selected-model",
        "provider_arguments": '{"city":"Seoul"}',
    }


async def test_provider_tool_calls_require_a_declared_catalog() -> None:
    """Complete and stream reject provider tools the caller did not authorize."""
    tool_call: dict[str, object] = {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "lookup_weather",
            "arguments": '{"city":"Seoul"}',
        },
    }
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "weather"),))
    _FakeCompletions.completion = _completion(
        content=None,
        finish_reason="tool_calls",
        tool_calls=[tool_call],
    )

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(_target(), request)

    _FakeCompletions.chunks = (
        _chunk(delta={"tool_calls": [{"index": 0, **tool_call}]}),
        _chunk(finish_reason="tool_calls"),
    )
    with pytest.raises(LlmResponseError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]


async def test_required_tool_choice_rejects_zero_calls() -> None:
    """Complete and stream cannot silently weaken REQUIRED to AUTO."""
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
        tool_calling=ToolCallingSpec(
            tools=(_tool_spec(),),
            choice=ModelToolChoice.REQUIRED,
        ),
    )
    _FakeCompletions.completion = _completion()

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(_target(), request)

    _FakeCompletions.chunks = (_chunk(finish_reason="stop"),)
    with pytest.raises(LlmResponseError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]


async def test_stream_maps_text_reasoning_structured_output_and_usage() -> None:
    """Streaming emits portable deltas, validated output, usage, and closes SDK resources."""
    _FakeCompletions.chunks = (
        _chunk(delta={"content": '{"answer":"'}),
        _chunk(delta={"content": 'ok"}', "reasoning_content": "thinking"}),
        _chunk(finish_reason="stop"),
        _chunk(
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 6,
                "total_tokens": 11,
            }
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "question"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=_schema())
        ),
        streaming=StreamingOptions(include_usage=True),
    )

    events = [
        event
        async for event in OpenAIChatProvider().stream(
            _target(supports_reasoning=True), request
        )
    ]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.REASONING_DELTA,
        ModelStreamEventKind.STRUCTURED_OUTPUT,
        ModelStreamEventKind.DONE,
    ]
    assert events[2].reasoning_delta == "thinking"
    assert events[3].structured_output == {"answer": "ok"}
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 11
    assert events[-1].metadata == {
        "model_ref": "support/primary",
        "provider": "openai",
        "profile": "vllm-local",
        "model": "selected-model",
        "finish_reason": "stop",
    }
    assert _FakeCompletions.calls[0]["stream_options"] == {"include_usage": True}
    assert _FakeCompletions.calls[0]["timeout"] == 22.0
    assert _FakeCompletions.stream is not None
    assert _FakeCompletions.stream.entered is True
    assert _FakeCompletions.stream.exited is True
    assert _FakeAsyncOpenAI.exited is True


async def test_stream_rejects_truncated_structured_output() -> None:
    """Every structured stream is decoded even when the SDK reports truncation."""
    _FakeCompletions.chunks = (
        _chunk(delta={"content": '{"answer":"partial'}),
        _chunk(finish_reason="length"),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "question"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=_schema())
        ),
    )

    with pytest.raises(LlmResponseError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]


async def test_stream_maps_incremental_function_tool_lifecycle() -> None:
    """Tool name and argument chunks become start, delta, end, and candidate events."""
    _FakeCompletions.chunks = (
        _chunk(
            delta={
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "lookup_weather",
                            "arguments": '{"city":"',
                        },
                    }
                ]
            }
        ),
        _chunk(
            delta={
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": 'Seoul"}'},
                    }
                ]
            },
            finish_reason="tool_calls",
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
        tool_calling=ToolCallingSpec(tools=(_tool_spec(),)),
    )

    events = [event async for event in OpenAIChatProvider().stream(_target(), request)]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOOL_CALL_START,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_END,
        ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        ModelStreamEventKind.DONE,
    ]
    assert events[1].tool_call_args_delta == '{"city":"'
    assert events[2].tool_call_args_delta == 'Seoul"}'
    assert events[3].tool_call is not None
    assert events[3].tool_call.arguments == {"city": "Seoul"}
    assert events[4].tool_call == events[3].tool_call


async def test_stream_validates_structured_output_before_tool_candidate() -> None:
    """Invalid structured output cannot authorize an otherwise valid tool call."""
    _FakeCompletions.chunks = (
        _chunk(
            delta={
                "content": '{"answer":3}',
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "lookup_weather",
                            "arguments": '{"city":"Seoul"}',
                        },
                    }
                ],
            },
            finish_reason="tool_calls",
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=_schema())
        ),
        tool_calling=ToolCallingSpec(tools=(_tool_spec(),)),
    )
    observed: list[ModelStreamEvent] = []

    with pytest.raises(LlmResponseError):
        async for event in OpenAIChatProvider().stream(_target(), request):
            observed.append(event)

    assert all(
        event.kind is not ModelStreamEventKind.TOOL_CALL_CANDIDATE for event in observed
    )


async def test_stream_validates_every_tool_before_first_candidate() -> None:
    """One invalid call makes a multi-tool terminal batch atomically unusable."""
    _FakeCompletions.chunks = (
        _chunk(
            delta={
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "lookup_weather",
                            "arguments": '{"city":"Seoul"}',
                        },
                    },
                    {
                        "index": 1,
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "lookup_weather",
                            "arguments": '{"city":3}',
                        },
                    },
                ]
            },
            finish_reason="tool_calls",
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
        tool_calling=ToolCallingSpec(tools=(_tool_spec(),)),
    )
    observed: list[ModelStreamEvent] = []

    with pytest.raises(LlmResponseError):
        async for event in OpenAIChatProvider().stream(_target(), request):
            observed.append(event)

    assert all(
        event.kind is not ModelStreamEventKind.TOOL_CALL_CANDIDATE for event in observed
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            APITimeoutError(httpx2.Request("POST", "https://api.openai.com")),
            LlmTimeoutError,
        ),
        (
            APIConnectionError(
                request=httpx2.Request("POST", "https://api.openai.com")
            ),
            LlmTransportError,
        ),
        (
            APIStatusError(
                "rate limited",
                response=httpx2.Response(
                    429,
                    request=httpx2.Request("POST", "https://api.openai.com"),
                ),
                body=None,
            ),
            LlmTransportError,
        ),
        (
            APIStatusError(
                "gateway timeout",
                response=httpx2.Response(
                    504,
                    request=httpx2.Request("POST", "https://api.openai.com"),
                ),
                body=None,
            ),
            LlmTimeoutError,
        ),
        (
            APIStatusError(
                "bad request",
                response=httpx2.Response(
                    400,
                    request=httpx2.Request("POST", "https://api.openai.com"),
                ),
                body=None,
            ),
            LlmResponseError,
        ),
        (
            APIResponseValidationError(
                httpx2.Response(
                    200,
                    request=httpx2.Request("POST", "https://api.openai.com"),
                ),
                None,
            ),
            LlmResponseError,
        ),
    ],
)
async def test_complete_normalizes_official_sdk_failures(
    error: BaseException,
    expected: type[BaseException],
) -> None:
    """SDK transport, timeout, status, and validation failures use generic errors."""
    _FakeCompletions.error = error

    with pytest.raises(expected):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_stream_normalizes_iteration_sdk_failure() -> None:
    """SDK failures raised before stream creation use the same generic boundary."""
    _FakeCompletions.error = APIConnectionError(
        request=httpx2.Request("POST", "https://api.openai.com")
    )

    with pytest.raises(LlmTransportError):
        _ = [
            event
            async for event in OpenAIChatProvider().stream(
                _target(),
                ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
            )
        ]


@pytest.mark.parametrize(
    "completion",
    [
        _completion(refusal="no"),
        _completion(finish_reason="content_filter"),
    ],
)
async def test_complete_maps_provider_refusal(completion: ChatCompletion) -> None:
    """Explicit refusal and content-filter finishes become a generic refusal."""
    _FakeCompletions.completion = completion

    with pytest.raises(LlmModelRefusalError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_complete_rejects_tool_call_when_choice_is_none() -> None:
    """A provider cannot bypass the request's explicit tool opt-out."""
    _FakeCompletions.completion = _completion(
        content=None,
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "lookup_weather",
                    "arguments": '{"city":"Seoul"}',
                },
            }
        ],
    )

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "weather"),),
                tool_calling=ToolCallingSpec(
                    tools=(_tool_spec(),),
                    choice=ModelToolChoice.NONE,
                ),
            ),
        )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (
            _target(
                dialect=OpenAICompatibleDialect.STANDARD,
                api_key=None,
                base_url=None,
            ),
            LlmConfigurationError,
        ),
        (
            _target(api_key=None, base_url=None),
            LlmConfigurationError,
        ),
        (
            _foreign_target(),
            LlmUnsupportedFeatureError,
        ),
    ],
)
async def test_complete_rejects_invalid_profile_target(
    target: LlmModelTarget,
    expected: type[BaseException],
) -> None:
    """Direct provider use remains fenced to a valid allowlisted OpenAI target."""
    with pytest.raises(expected):
        await OpenAIChatProvider().complete(
            target,
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_vllm_without_api_key_uses_nonsecret_sdk_sentinel() -> None:
    """An unauthenticated vLLM endpoint never falls back to ambient OpenAI credentials."""
    _FakeCompletions.completion = _completion()

    await OpenAIChatProvider().complete(
        _target(api_key=None), ModelRequest(messages=())
    )

    assert _FakeAsyncOpenAI.init_calls[0]["api_key"] == "not-required"


async def test_standard_profile_fences_ambient_openai_connection_metadata(
    monkeypatch: MonkeyPatch,
) -> None:
    """Ambient OpenAI routing metadata cannot alter an allowlisted profile."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "ambient-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "ambient-project")
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(openai_module, "AsyncOpenAI", SdkAsyncOpenAI)

    client = OpenAIChatProvider()._client(
        _target(
            dialect=OpenAICompatibleDialect.STANDARD,
            base_url=None,
        )
    )
    try:
        assert str(client.base_url) == "https://api.openai.com/v1/"
        assert client.organization == ""
        assert client.project == ""
        assert "ambient-org" not in client.default_headers.values()
        assert "ambient-project" not in client.default_headers.values()
    finally:
        await client.close()


@pytest.mark.parametrize(
    ("operation", "headers", "body"),
    [
        ("complete", {"content-type": "application/json"}, b"not-json"),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"choices":[1]}',
        ),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"id":"chat-1","choices":[{"index":0,"finish_reason":null,'
            b'"message":{"role":"assistant","content":"ok"}}],"created":1,'
            b'"model":"model","object":"chat.completion"}',
        ),
        (
            "complete",
            {"content-type": "application/json"},
            b'{"id":"chat-1","choices":[{"index":0,'
            b'"finish_reason":"future_reason","message":'
            b'{"role":"assistant","content":"ok"}}],"created":1,'
            b'"model":"model","object":"chat.completion"}',
        ),
        ("stream", {"content-type": "text/event-stream"}, b"data: not-json\n\n"),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b'data: {"choices":[1]}\n\ndata: [DONE]\n\n',
        ),
        (
            "stream",
            {"content-type": "text/event-stream"},
            b'data: {"id":"chat-1","choices":[{"index":0,'
            b'"finish_reason":"future_reason","delta":{"role":"assistant",'
            b'"content":"ok"}}],"created":1,"model":"model",'
            b'"object":"chat.completion.chunk"}\n\ndata: [DONE]\n\n',
        ),
    ],
)
async def test_installed_openai_sdk_rejects_malformed_success_payloads(
    monkeypatch: MonkeyPatch,
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
            openai_module,
            "AsyncOpenAI",
            partial(SdkAsyncOpenAI, http_client=http_client),
        )
        provider = OpenAIChatProvider()
        request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

        with pytest.raises(LlmResponseError):
            if operation == "complete":
                await provider.complete(_target(), request)
            else:
                _ = [event async for event in provider.stream(_target(), request)]


def test_openai_profile_rejects_ambient_custom_headers(
    monkeypatch: MonkeyPatch,
) -> None:
    """SDK-specific ambient headers cannot extend the profile header allowlist."""
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "X-Ambient: injected")

    with pytest.raises(LlmConfigurationError):
        OpenAIChatProvider()._client(_target())


@pytest.mark.parametrize(
    "message",
    [
        ModelMessage(ModelMessageRole.TOOL, "result"),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": "invalid"},
        ),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={
                "tool_calls": ({"id": "call-1", "name": "tool", "arguments": 3},)
            },
        ),
    ],
)
async def test_complete_rejects_malformed_tool_history(message: ModelMessage) -> None:
    """Tool history must carry the neutral call metadata needed by OpenAI."""
    _FakeCompletions.completion = _completion()

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(message,)),
        )


async def test_complete_maps_assistant_history_with_serialized_arguments() -> None:
    """Already serialized assistant tool arguments pass through unchanged."""
    _FakeCompletions.completion = _completion()
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.ASSISTANT, "plain answer"),
            ModelMessage(
                ModelMessageRole.ASSISTANT,
                "",
                metadata={
                    "tool_calls": (
                        {
                            "id": "call-1",
                            "name": "lookup_weather",
                            "arguments": '{"city":"Busan"}',
                        },
                    )
                },
            ),
        )
    )

    await OpenAIChatProvider().complete(_target(), request)

    messages = _FakeCompletions.calls[0]["messages"]
    assert messages == [
        {"role": "assistant", "content": "plain answer"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "arguments": '{"city":"Busan"}',
                    },
                }
            ],
        },
    ]


@pytest.mark.parametrize(
    "message",
    [
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": (1,)},
        ),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={"tool_calls": ({"name": "lookup_weather", "arguments": "{}"},)},
        ),
    ],
)
async def test_complete_rejects_additional_malformed_tool_history(
    message: ModelMessage,
) -> None:
    """Tool history entries require mapping shape, id, name, and arguments."""
    _FakeCompletions.completion = _completion()

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(message,)),
        )


async def test_complete_rejects_empty_declared_tool_catalog() -> None:
    """A tool-calling request cannot declare an empty provider catalog."""
    _FakeCompletions.completion = _completion()

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
                tool_calling=ToolCallingSpec(tools=()),
            ),
        )


async def test_complete_vllm_without_extensions_omits_extra_body() -> None:
    """A plain vLLM request does not send an empty provider extension object."""
    _FakeCompletions.completion = _completion()
    target = _target(include_vllm_extensions=False)

    await OpenAIChatProvider().complete(
        target,
        ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
    )

    call = _FakeCompletions.calls[0]
    assert call["extra_body"] is None
    assert call["max_tokens"] is omit
    assert call["temperature"] is omit
    assert call["top_p"] is omit


async def test_complete_rejects_empty_choice_and_empty_message() -> None:
    """Malformed success responses cannot cross the provider boundary."""
    _FakeCompletions.completion = ChatCompletion.model_validate(
        {
            "id": "empty",
            "created": 1,
            "model": "served-model",
            "object": "chat.completion",
            "choices": [],
        }
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(_target(), request)

    _FakeCompletions.completion = _completion(content=None)
    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(_target(), request)


async def test_complete_rejects_custom_tool_call() -> None:
    """The function-tool contract does not silently accept OpenAI custom tools."""
    _FakeCompletions.completion = _completion(
        content=None,
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "custom-1",
                "type": "custom",
                "custom": {"name": "shell", "input": "pwd"},
            }
        ],
    )

    with pytest.raises(LlmUnsupportedFeatureError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_complete_rejects_tool_finish_without_tool_calls() -> None:
    """A tool terminal reason must correspond to at least one validated call."""
    _FakeCompletions.completion = _completion(
        content="missing tool",
        finish_reason="tool_calls",
    )
    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_complete_rejects_legacy_function_call_terminal() -> None:
    """The removed legacy function_call terminal cannot masquerade as plain text."""
    completion = _completion()
    completion.choices[0].finish_reason = "function_call"
    _FakeCompletions.completion = completion

    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(
            _target(),
            ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
        )


async def test_complete_without_usage_returns_empty_usage() -> None:
    """Usage remains optional when an OpenAI-compatible server omits it."""
    completion = _completion()
    completion.usage = None
    _FakeCompletions.completion = completion

    response = await OpenAIChatProvider().complete(
        _target(),
        ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
    )

    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None
    assert response.usage.total_tokens is None


@pytest.mark.parametrize(
    "chunks",
    [
        (_chunk(delta={"refusal": "no"}),),
        (_chunk(finish_reason="content_filter"),),
    ],
)
async def test_stream_maps_provider_refusal(
    chunks: tuple[ChatCompletionChunk, ...],
) -> None:
    """Streaming refusal signals fail through the generic refusal boundary."""
    _FakeCompletions.chunks = chunks

    with pytest.raises(LlmModelRefusalError):
        _ = [
            event
            async for event in OpenAIChatProvider().stream(
                _target(),
                ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
            )
        ]


async def test_stream_rejects_incomplete_tool_call_and_wrong_finish() -> None:
    """Incomplete tool buffers and non-tool terminal reasons fail closed."""
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        tool_calling=ToolCallingSpec(tools=(_tool_spec(),)),
    )
    _FakeCompletions.chunks = (
        _chunk(delta={"tool_calls": [{"index": 0, "id": "call-1"}]}),
        _chunk(finish_reason="tool_calls"),
    )
    with pytest.raises(LlmResponseError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]

    _FakeCompletions.chunks = (
        _chunk(
            delta={
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {"name": "lookup_weather", "arguments": "{}"},
                    }
                ]
            }
        ),
        _chunk(finish_reason="stop"),
    )
    with pytest.raises(LlmResponseError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]


async def test_stream_handles_named_tool_without_argument_delta() -> None:
    """A tool with omitted arguments is finalized as an empty object."""
    _FakeCompletions.chunks = (
        _chunk(
            delta={
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {"name": "ping"},
                    }
                ]
            },
            finish_reason="tool_calls",
        ),
    )

    events = [
        event
        async for event in OpenAIChatProvider().stream(
            _target(),
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "ping"),),
                tool_calling=ToolCallingSpec(
                    tools=(
                        ModelToolSpec(
                            name="ping",
                            parameters=JsonSchemaConstraint(
                                schema={
                                    "type": "object",
                                    "additionalProperties": False,
                                }
                            ),
                        ),
                    )
                ),
            ),
        )
    ]

    assert events[-2].kind == ModelStreamEventKind.TOOL_CALL_CANDIDATE
    assert events[-2].tool_call is not None
    assert events[-2].tool_call.arguments == {}


async def test_stream_rejects_nontext_reasoning_extension() -> None:
    """A malformed reasoning extension cannot leak an untyped payload."""
    _FakeCompletions.chunks = (_chunk(delta={"reasoning_content": 3}),)

    with pytest.raises(LlmResponseError):
        _ = [
            event
            async for event in OpenAIChatProvider().stream(
                _target(supports_reasoning=True),
                ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
            )
        ]


async def test_stream_rejects_eof_without_terminal_finish_reason() -> None:
    """An error-free early EOF cannot publish a partial assistant response as DONE."""
    _FakeCompletions.chunks = (_chunk(delta={"content": "partial"}),)

    with pytest.raises(LlmResponseError):
        _ = [
            event
            async for event in OpenAIChatProvider().stream(
                _target(),
                ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),)),
            )
        ]


async def test_stream_disables_usage_request_and_normalizes_iteration_error() -> None:
    """Usage opt-out is forwarded and late SDK transport failures are normalized."""
    _FakeCompletions.stream_error = APIConnectionError(
        request=httpx2.Request("POST", "https://api.openai.com")
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        streaming=StreamingOptions(include_usage=False),
    )

    with pytest.raises(LlmTransportError):
        _ = [event async for event in OpenAIChatProvider().stream(_target(), request)]

    assert _FakeCompletions.calls[0]["stream_options"] is omit


async def test_stream_ignores_unsolicited_usage_when_disabled() -> None:
    """An endpoint cannot override the caller's usage accounting opt-out."""
    _FakeCompletions.chunks = (
        _chunk(finish_reason="stop"),
        _chunk(
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 6,
                "total_tokens": 11,
            }
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        streaming=StreamingOptions(include_usage=False),
    )

    events = [event async for event in OpenAIChatProvider().stream(_target(), request)]

    assert events[-1].kind is ModelStreamEventKind.DONE
    assert events[-1].usage is None


async def test_complete_maps_server_error_and_generic_sdk_error() -> None:
    """Retriable server status and other SDK failures map deterministically."""
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))
    _FakeCompletions.error = APIStatusError(
        "server error",
        response=httpx2.Response(
            500,
            request=httpx2.Request("POST", "https://api.openai.com"),
        ),
        body=None,
    )
    with pytest.raises(LlmTransportError):
        await OpenAIChatProvider().complete(_target(), request)

    _FakeCompletions.error = openai_module.APIError(
        "other",
        request=httpx2.Request("POST", "https://api.openai.com"),
        body=None,
    )
    with pytest.raises(LlmResponseError):
        await OpenAIChatProvider().complete(_target(), request)
