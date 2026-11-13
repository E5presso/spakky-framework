"""Unit tests for the OpenAI Responses provider over a fake SSE transport."""

from collections.abc import AsyncIterator, Mapping, Sequence
from json import dumps, loads
from typing import cast, override

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    AsyncOpenAI as SdkAsyncOpenAI,
    omit,
)
from pydantic import SecretStr
from pytest import MonkeyPatch
from spakky.agent import (
    AudioPart,
    DocumentPart,
    ImagePart,
    JsonSchemaConstraint,
    JsonValue,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelModality,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelToolSpec,
    ModelUsage,
    SamplingOptions,
    StreamingOptions,
    StructuredOutputSpec,
    TextPart,
    ToolCallingSpec,
    VideoPart,
)
from spakky.agent.content import ModelContentPart

from spakky.plugins.llm.config import (
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    LlmReasoningEffort,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmFailureClass,
    LlmModelRefusalError,
    LlmQuotaExhaustedError,
    LlmRateLimitError,
    LlmResponseError,
    LlmStreamInterruptedError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.provider import (
    ILLMCredentialProvider,
    LlmAccessToken,
    LlmCredentialRequest,
    LlmModelTarget,
    failure_code,
    to_model_error,
)
from spakky.plugins.llm.providers import openai_responses as responses_module
from spakky.plugins.llm.providers.openai_responses import OpenAIResponsesProvider

type _Reply = httpx2.Response | BaseException


class _FailingByteStream(httpx2.AsyncByteStream):
    """Yield one SSE prefix and then fail like a dropped connection."""

    def __init__(self, prefix: bytes, error: BaseException) -> None:
        self._prefix = prefix
        self._error = error

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._prefix
        raise self._error


class _Wire:
    """Scripted HTTP exchange recorded behind the real OpenAI SDK client."""

    def __init__(self) -> None:
        self.replies: list[_Reply] = []
        self.requests: list[httpx2.Request] = []
        self.client_kwargs: list[dict[str, object]] = []

    def client(
        self,
        *,
        api_key: str,
        admin_api_key: str,
        base_url: str,
        organization: str,
        project: str,
        webhook_secret: str,
        timeout: float | None,
        max_retries: int,
        default_headers: dict[str, str],
    ) -> SdkAsyncOpenAI:
        self.client_kwargs.append({"timeout": timeout, "base_url": base_url})
        return SdkAsyncOpenAI(
            api_key=api_key,
            admin_api_key=admin_api_key,
            base_url=base_url,
            organization=organization,
            project=project,
            webhook_secret=webhook_secret,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(self._handle)
            ),
        )

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def body(self, index: int = 0) -> Mapping[str, object]:
        return cast(Mapping[str, object], loads(self.requests[index].content))

    def bearer(self, index: int = 0) -> str:
        return self.requests[index].headers["authorization"]


@pytest.fixture
def wire(monkeypatch: MonkeyPatch) -> _Wire:
    wire = _Wire()
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(responses_module, "AsyncOpenAI", wire.client)
    return wire


def _sse(*events: Mapping[str, object]) -> httpx2.Response:
    return httpx2.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=_sse_bytes(*events),
    )


def _sse_bytes(*events: Mapping[str, object]) -> bytes:
    return b"".join(
        f"event: {event['type']}\ndata: {dumps(event)}\n\n".encode() for event in events
    )


def _http_error(
    status: int,
    code: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx2.Response:
    return httpx2.Response(
        status,
        headers=dict(headers or {}),
        json={"error": {"message": "rejected", "code": code}},
    )


def _response(
    *,
    status: str = "completed",
    usage: bool = True,
    error_code: str | None = None,
    incomplete_reason: str | None = None,
    has_error: bool = True,
    has_incomplete_details: bool = True,
) -> dict[str, object]:
    response: dict[str, object] = {
        "id": "resp-1",
        "object": "response",
        "model": "served-model",
        "status": status,
        "output": [],
    }
    if usage:
        response["usage"] = {
            "input_tokens": 7,
            "output_tokens": 5,
            "total_tokens": 12,
            "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 1},
        }
    if status == "failed" and has_error:
        response["error"] = {"code": error_code, "message": "failed"}
    if status == "incomplete" and has_incomplete_details:
        response["incomplete_details"] = {"reason": incomplete_reason}
    return response


def _completed(*, status: str = "completed", usage: bool = True) -> dict[str, object]:
    return {
        "type": "response.completed",
        "sequence_number": 99,
        "response": _response(status=status, usage=usage),
    }


def _text_delta(delta: str) -> dict[str, object]:
    return {
        "type": "response.output_text.delta",
        "delta": delta,
        "item_id": "msg-1",
        "output_index": 0,
        "content_index": 0,
        "sequence_number": 1,
        "logprobs": [],
    }


def _function_item(arguments: str = "", index: int = 0) -> dict[str, object]:
    return {
        "type": "function_call",
        "id": f"fc-{index}",
        "call_id": f"call-{index}",
        "name": "lookup_weather",
        "arguments": arguments,
    }


def _item_event(
    kind: str,
    item: Mapping[str, object],
    index: int = 0,
) -> dict[str, object]:
    return {
        "type": f"response.output_item.{kind}",
        "output_index": index,
        "sequence_number": 2,
        "item": item,
    }


def _arguments_delta(delta: str, index: int = 0) -> dict[str, object]:
    return {
        "type": "response.function_call_arguments.delta",
        "delta": delta,
        "item_id": f"fc-{index}",
        "output_index": index,
        "sequence_number": 3,
    }


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
            },
        ),
    )


def _tools(choice: ModelToolChoice = ModelToolChoice.AUTO) -> ToolCallingSpec:
    return ToolCallingSpec(tools=(_tool_spec(),), choice=choice)


def _answer_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def _target(
    *,
    dialect: OpenAICompatibleDialect = OpenAICompatibleDialect.STANDARD,
    api_key: SecretStr | None = SecretStr("secret"),
    credential_provider: str | None = None,
    base_url: str | None = None,
    supports_reasoning: bool = False,
    reasoning_effort: LlmReasoningEffort | None = None,
    input_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT}),
) -> LlmModelTarget:
    return LlmModelTarget(
        model_ref="builder/primary",
        profile_name="openai-responses",
        profile=LlmProfile(
            provider="openai",
            api=LlmProviderApi.OPENAI_RESPONSES,
            api_key=api_key,
            credential_provider=credential_provider,
            base_url=base_url,
            openai_dialect=dialect,
            request_timeout_seconds=11,
            stream_timeout_seconds=22,
            headers={"X-Tenant": "tenant-a"},
        ),
        route=LlmModelRoute(
            profile="openai-responses",
            model="selected-model",
            capability=ModelCapability(
                supports_reasoning=supports_reasoning,
                input_modalities=input_modalities,
            ),
            reasoning_effort=reasoning_effort,
        ),
    )


def _request(
    *,
    tool_calling: ToolCallingSpec | None = None,
    structured_output: StructuredOutputSpec | None = None,
    sampling: SamplingOptions | None = None,
    streaming: StreamingOptions | None = None,
) -> ModelRequest:
    return ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "Be brief."),
            ModelMessage.user("hello"),
        ),
        tool_calling=tool_calling,
        structured_output=structured_output,
        sampling=sampling if sampling is not None else SamplingOptions(),
        streaming=streaming if streaming is not None else StreamingOptions(),
    )


async def _collect(
    provider: OpenAIResponsesProvider,
    target: LlmModelTarget,
    request: ModelRequest,
) -> list[ModelStreamEvent]:
    return [event async for event in provider.stream(target, request)]


class _RecordingCredentialProvider(ILLMCredentialProvider):
    def __init__(self, tokens: Sequence[str], name: str = "chatgpt") -> None:
        self._tokens = list(tokens)
        self._name = name
        self.requests: list[LlmCredentialRequest] = []

    @property
    @override
    def name(self) -> str:
        return self._name

    @override
    async def access_token(self, credential: LlmCredentialRequest) -> LlmAccessToken:
        self.requests.append(credential)
        return self._tokens.pop(0)


def test_responses_provider_expect_default_responses_api_adapter() -> None:
    """The adapter registers as the replaceable default for openai-responses."""
    provider = OpenAIResponsesProvider()

    assert provider.apis == frozenset({LlmProviderApi.OPENAI_RESPONSES})
    assert provider.is_default is True


async def test_stream_text_expect_tokens_usage_and_stateless_request(
    wire: _Wire,
) -> None:
    """A text turn maps deltas, usage, and a store=false streaming request."""
    wire.replies = [
        _sse(
            {"type": "response.created", "sequence_number": 0, "response": _response()},
            _text_delta("Hel"),
            _text_delta(""),
            _text_delta("lo"),
            _completed(),
        )
    ]
    request = _request(
        sampling=SamplingOptions(temperature=0.2, top_p=0.9, max_tokens=64),
    )

    events = await _collect(OpenAIResponsesProvider(), _target(), request)

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.DONE,
    ]
    assert [event.token_delta for event in events[:2]] == ["Hel", "lo"]
    assert events[-1].usage == ModelUsage(
        input_tokens=7,
        output_tokens=5,
        total_tokens=12,
        cached_input_tokens=3,
        cache_write_input_tokens=2,
    )
    assert events[-1].metadata["finish_reason"] == "stop"
    assert events[-1].metadata["response_id"] == "resp-1"
    assert events[-1].metadata["response_model"] == "served-model"
    assert events[-1].metadata["model_ref"] == "builder/primary"
    assert str(wire.requests[0].url) == "https://api.openai.com/v1/responses"
    assert wire.bearer() == "Bearer secret"
    assert wire.requests[0].headers["x-tenant"] == "tenant-a"
    body = wire.body()
    assert body["model"] == "selected-model"
    assert body["stream"] is True
    assert body["store"] is False
    assert body["temperature"] == 0.2
    assert body["top_p"] == 0.9
    assert body["max_output_tokens"] == 64
    assert body["input"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "hello"},
    ]
    assert "tools" not in body
    assert "text" not in body
    assert "reasoning" not in body
    assert wire.client_kwargs[0]["timeout"] == 11
    assert wire.client_kwargs[0]["base_url"] == "https://api.openai.com/v1"


async def test_stream_without_usage_request_expect_done_without_usage(
    wire: _Wire,
) -> None:
    """Usage is reported on the stream only when the caller asks for it."""
    wire.replies = [_sse(_text_delta("ok"), _completed())]

    events = await _collect(
        OpenAIResponsesProvider(),
        _target(base_url="https://gateway.example.test/v1"),
        _request(streaming=StreamingOptions(include_usage=False)),
    )

    assert events[-1].usage is None
    assert str(wire.requests[0].url) == "https://gateway.example.test/v1/responses"


async def test_chatgpt_dialect_expect_plan_request_shape(wire: _Wire) -> None:
    """ChatGPT sign-in drops sampling, uses developer role, and namespaces tools."""
    wire.replies = [
        _sse(
            _item_event("added", _function_item()),
            _arguments_delta('{"city":'),
            _arguments_delta('"Seoul"}'),
            _item_event("done", _function_item('{"city":"Seoul"}')),
            _completed(),
        )
    ]
    history = (
        ModelMessage(ModelMessageRole.SYSTEM, "Be brief."),
        ModelMessage.user("weather?"),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={
                "tool_calls": (
                    {"id": "call-9", "name": "lookup_weather", "arguments": "{}"},
                )
            },
        ),
        ModelMessage(
            ModelMessageRole.TOOL,
            "sunny",
            metadata={"call_id": "call-9", "tool_name": "lookup_weather"},
        ),
    )
    request = ModelRequest(
        messages=history,
        tool_calling=_tools(ModelToolChoice.REQUIRED),
        sampling=SamplingOptions(temperature=0.2, top_p=0.9, max_tokens=64),
    )
    target = _target(
        dialect=OpenAICompatibleDialect.CHATGPT,
        reasoning_effort=LlmReasoningEffort.LOW,
    )

    events = await _collect(OpenAIResponsesProvider(), target, request)

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOOL_CALL_START,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
        ModelStreamEventKind.TOOL_CALL_END,
        ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        ModelStreamEventKind.DONE,
    ]
    assert events[1].tool_call_args_delta == '{"city":'
    candidate = events[4].tool_call
    assert candidate is not None
    assert candidate.name == "lookup_weather"
    assert candidate.call_id == "call-0"
    assert candidate.arguments == {"city": "Seoul"}
    assert candidate.metadata["provider_arguments"] == '{"city":"Seoul"}'
    assert events[-1].metadata["finish_reason"] == "tool_calls"
    body = wire.body()
    assert "temperature" not in body
    assert "top_p" not in body
    assert "max_output_tokens" not in body
    assert body["store"] is False
    assert body["tool_choice"] == "required"
    assert body["reasoning"] == {"effort": "low"}
    assert body["input"] == [
        {"role": "developer", "content": "Be brief."},
        {"role": "user", "content": "weather?"},
        {
            "type": "function_call",
            "call_id": "call-9",
            "name": "lookup_weather",
            "arguments": "{}",
            "namespace": "functions",
        },
        {"type": "function_call_output", "call_id": "call-9", "output": "sunny"},
    ]
    tools = cast(Sequence[Mapping[str, object]], body["tools"])
    assert len(tools) == 1
    assert tools[0]["type"] == "namespace"
    assert tools[0]["name"] == "functions"
    functions = cast(Sequence[Mapping[str, object]], tools[0]["tools"])
    assert functions[0]["type"] == "function"
    assert functions[0]["name"] == "lookup_weather"
    assert functions[0]["description"] == "Look up weather"
    assert functions[0]["strict"] is True


@pytest.mark.parametrize(
    ("choice", "expected"),
    [(ModelToolChoice.AUTO, "auto"), (ModelToolChoice.NONE, "none")],
)
async def test_standard_dialect_expect_flat_function_tools(
    wire: _Wire,
    choice: ModelToolChoice,
    expected: str,
) -> None:
    """API-key Responses profiles send flat function tools and plain history."""
    wire.replies = [_sse(_text_delta("ok"), _completed())]
    history = (
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "calling",
            metadata={
                "tool_calls": (
                    {"id": "call-9", "name": "lookup_weather", "arguments": {"q": 1}},
                )
            },
        ),
    )

    await _collect(
        OpenAIResponsesProvider(),
        _target(),
        ModelRequest(messages=history, tool_calling=_tools(choice)),
    )

    body = wire.body()
    assert body["tool_choice"] == expected
    tools = cast(Sequence[Mapping[str, object]], body["tools"])
    assert tools[0]["type"] == "function"
    assert tools[0]["name"] == "lookup_weather"
    assert body["input"] == [
        {"role": "assistant", "content": "calling"},
        {
            "type": "function_call",
            "call_id": "call-9",
            "name": "lookup_weather",
            "arguments": '{"q":1}',
        },
    ]


async def test_assistant_text_history_expect_plain_assistant_message(
    wire: _Wire,
) -> None:
    """Assistant text without tool calls is replayed as one assistant message."""
    wire.replies = [_sse(_text_delta("ok"), _completed())]
    history = (
        ModelMessage.user("hi"),
        ModelMessage(ModelMessageRole.ASSISTANT, "hello"),
        ModelMessage.user("again"),
    )

    await OpenAIResponsesProvider().complete(_target(), ModelRequest(messages=history))

    assert wire.body()["input"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]


async def test_complete_expect_aggregated_stream_with_reasoning(wire: _Wire) -> None:
    """complete() always streams and aggregates text, tools, usage, and reasoning."""
    wire.replies = [
        _sse(
            {
                "type": "response.reasoning_summary_text.delta",
                "delta": "think ",
                "item_id": "rs-1",
                "output_index": 0,
                "summary_index": 0,
                "sequence_number": 1,
            },
            {
                "type": "response.reasoning_text.delta",
                "delta": "more",
                "item_id": "rs-1",
                "output_index": 0,
                "content_index": 0,
                "sequence_number": 2,
            },
            _item_event("added", {"type": "reasoning", "id": "rs-1", "summary": []}),
            _text_delta("calling"),
            _item_event("added", _function_item(index=1), index=1),
            _arguments_delta('{"city":"Busan"}', index=1),
            _completed(),
        )
    ]
    target = _target(
        supports_reasoning=True,
        reasoning_effort=LlmReasoningEffort.HIGH,
    )

    response = await OpenAIResponsesProvider().complete(
        target,
        _request(tool_calling=_tools()),
    )

    assert response.content == "calling"
    assert response.tool_calls[0].arguments == {"city": "Busan"}
    assert response.tool_calls[0].call_id == "call-1"
    assert response.usage.total_tokens == 12
    assert response.metadata["reasoning"] == "think more"
    assert response.metadata["finish_reason"] == "tool_calls"
    assert response.metadata["response_id"] == "resp-1"
    body = wire.body()
    assert body["stream"] is True
    assert body["reasoning"] == {"effort": "high", "summary": "auto"}
    assert wire.client_kwargs[0]["timeout"] == 11


async def test_reasoning_capable_route_without_effort_expect_summary_only(
    wire: _Wire,
) -> None:
    """A reasoning-capable route asks for summaries without forcing an effort."""
    wire.replies = [_sse(_text_delta("ok"), _completed(usage=False))]

    response = await OpenAIResponsesProvider().complete(
        _target(supports_reasoning=True),
        _request(),
    )

    assert response.usage == ModelUsage()
    assert "reasoning" not in response.metadata
    assert wire.body()["reasoning"] == {"summary": "auto"}


async def test_reasoning_delta_without_capability_expect_suppressed(
    wire: _Wire,
) -> None:
    """Reasoning text is dropped when the route does not declare reasoning."""
    wire.replies = [
        _sse(
            {
                "type": "response.reasoning_summary_text.delta",
                "delta": "hidden",
                "item_id": "rs-1",
                "output_index": 0,
                "summary_index": 0,
                "sequence_number": 1,
            },
            _text_delta("ok"),
            _completed(),
        )
    ]

    events = await _collect(OpenAIResponsesProvider(), _target(), _request())

    assert ModelStreamEventKind.REASONING_DELTA not in [e.kind for e in events]


async def test_reasoning_delta_with_capability_expect_reasoning_events(
    wire: _Wire,
) -> None:
    """Declared reasoning routes surface non-empty reasoning deltas."""
    wire.replies = [
        _sse(
            {
                "type": "response.reasoning_summary_text.delta",
                "delta": "",
                "item_id": "rs-1",
                "output_index": 0,
                "summary_index": 0,
                "sequence_number": 1,
            },
            {
                "type": "response.reasoning_summary_text.delta",
                "delta": "plan",
                "item_id": "rs-1",
                "output_index": 0,
                "summary_index": 0,
                "sequence_number": 2,
            },
            _completed(),
        )
    ]

    events = await _collect(
        OpenAIResponsesProvider(),
        _target(supports_reasoning=True),
        _request(),
    )

    assert [event.reasoning_delta for event in events[:-1]] == ["plan"]


@pytest.mark.parametrize("strict", [True, False])
async def test_structured_output_expect_json_schema_text_format(
    wire: _Wire,
    strict: bool,
) -> None:
    """Structured output uses text.format json_schema and validates the result."""
    wire.replies = [
        _sse(_text_delta('{"answer":'), _text_delta('"42"}'), _completed()),
        _sse(_text_delta('{"answer":"42"}'), _completed()),
    ]
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["answer"],
        "additionalProperties": False,
    }
    request = _request(
        structured_output=StructuredOutputSpec(
            JsonSchemaConstraint(schema=schema, strict=strict),
            "Answer",
        ),
    )
    provider = OpenAIResponsesProvider()

    events = await _collect(provider, _target(), request)
    response = await provider.complete(_target(), request)

    assert events[-2].kind is ModelStreamEventKind.STRUCTURED_OUTPUT
    assert events[-2].structured_output == {"answer": "42"}
    assert response.structured_output == {"answer": "42"}
    text = cast(Mapping[str, object], wire.body()["text"])
    text_format = cast(Mapping[str, object], text["format"])
    wire_schema = cast(Mapping[str, object], text_format["schema"])
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "Answer"
    assert text_format["strict"] is strict
    assert wire_schema["required"] == (["answer", "note"] if strict else ["answer"])


async def test_structured_output_without_type_name_expect_default_name(
    wire: _Wire,
) -> None:
    """An unnamed structured output falls back to the neutral format name."""
    wire.replies = [_sse(_text_delta('{"answer":"42"}'), _completed())]

    await _collect(
        OpenAIResponsesProvider(),
        _target(),
        _request(
            structured_output=StructuredOutputSpec(
                JsonSchemaConstraint(schema=_answer_schema()),
            ),
        ),
    )

    text = cast(Mapping[str, object], wire.body()["text"])
    assert cast(Mapping[str, object], text["format"])["name"] == "structured_output"


async def test_structured_output_violating_schema_expect_response_error(
    wire: _Wire,
) -> None:
    """Provider output is re-validated locally even when strict was requested."""
    wire.replies = [_sse(_text_delta('{"other":1}'), _completed())]

    with pytest.raises(LlmResponseError):
        await OpenAIResponsesProvider().complete(
            _target(),
            _request(
                structured_output=StructuredOutputSpec(
                    JsonSchemaConstraint(schema=_answer_schema()),
                    "Answer",
                ),
            ),
        )


def test_strict_schema_expect_nested_objects_closed_and_required() -> None:
    """Strict wire schemas require every property at every object depth."""
    provider = OpenAIResponsesProvider()
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {
            "nested": {"type": "object", "properties": {"value": {"type": "integer"}}},
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"x": {"type": "string"}}},
            },
            "choice": {"anyOf": [{"type": "string"}, True]},
            "flag": True,
        },
    }

    wire_schema = provider._strict_response_schema(schema)

    properties = cast(Mapping[str, Mapping[str, object]], wire_schema["properties"])
    assert wire_schema["required"] == ("nested", "items", "choice", "flag")
    assert properties["nested"]["required"] == ("value",)
    assert properties["nested"]["additionalProperties"] is False
    items = cast(Mapping[str, object], properties["items"]["items"])
    assert items["required"] == ("x",)
    assert properties["choice"]["anyOf"] == ({"type": "string"}, True)
    assert properties["flag"] is True


def test_strict_schema_with_invalid_properties_expect_response_error() -> None:
    """A non-mapping properties value cannot be adapted to a strict schema."""
    with pytest.raises(LlmResponseError):
        OpenAIResponsesProvider()._strict_response_schema(
            {"type": "object", "properties": "invalid"}
        )


def test_strict_schema_with_open_mapping_expect_unsupported() -> None:
    """Strict adaptation fails instead of weakening arbitrary-key mappings."""
    with pytest.raises(LlmUnsupportedFeatureError):
        OpenAIResponsesProvider()._strict_response_schema(
            {"type": "object", "additionalProperties": {"type": "integer"}}
        )


async def test_incomplete_by_token_limit_expect_length_finish(wire: _Wire) -> None:
    """Hitting max_output_tokens is a successful truncated turn."""
    wire.replies = [
        _sse(
            _text_delta("partial"),
            {
                "type": "response.incomplete",
                "sequence_number": 9,
                "response": _response(
                    status="incomplete",
                    incomplete_reason="max_output_tokens",
                ),
            },
        )
    ]

    events = await _collect(OpenAIResponsesProvider(), _target(), _request())

    assert events[-1].metadata["finish_reason"] == "length"


@pytest.mark.parametrize("has_details", [True, False])
async def test_incomplete_by_filter_expect_refusal(
    wire: _Wire,
    has_details: bool,
) -> None:
    """Any other incomplete reason is treated as a refusal, never as success."""
    wire.replies = [
        _sse(
            {
                "type": "response.incomplete",
                "sequence_number": 9,
                "response": _response(
                    status="incomplete",
                    incomplete_reason="content_filter",
                    has_incomplete_details=has_details,
                ),
            }
        )
    ]

    with pytest.raises(LlmModelRefusalError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


async def test_refusal_delta_expect_refusal(wire: _Wire) -> None:
    """A streamed refusal is surfaced as a model refusal."""
    wire.replies = [
        _sse(
            {
                "type": "response.refusal.delta",
                "delta": "no",
                "item_id": "msg-1",
                "output_index": 0,
                "content_index": 0,
                "sequence_number": 1,
            }
        )
    ]

    with pytest.raises(LlmModelRefusalError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


async def test_completed_event_with_other_status_expect_response_error(
    wire: _Wire,
) -> None:
    """A completed event must carry the completed status."""
    wire.replies = [_sse(_completed(status="in_progress"))]

    with pytest.raises(LlmResponseError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("subscription_sharing_usage_limit_exceeded", LlmQuotaExhaustedError),
        ("subscription_sharing_usage_unavailable", LlmQuotaExhaustedError),
        ("insufficient_quota", LlmQuotaExhaustedError),
        ("rate_limit_exceeded", LlmRateLimitError),
        ("server_error", LlmTransportError),
        ("invalid_prompt", LlmResponseError),
    ],
)
async def test_failed_response_expect_error_classified_by_code(
    wire: _Wire,
    code: str,
    expected: type[AbstractLlmError],
) -> None:
    """response.failed is classified by provider code, quota apart from rate limit."""
    wire.replies = [
        _sse(
            _text_delta("partial"),
            {
                "type": "response.failed",
                "sequence_number": 9,
                "response": _response(status="failed", error_code=code),
            },
        )
    ]

    with pytest.raises(expected) as raised:
        await _collect(OpenAIResponsesProvider(), _target(), _request())

    assert type(raised.value) is expected
    assert raised.value.details["provider_code"] == code


async def test_failed_response_without_error_expect_response_error(
    wire: _Wire,
) -> None:
    """A failed response without an error object stays a response failure."""
    wire.replies = [
        _sse(
            {
                "type": "response.failed",
                "sequence_number": 9,
                "response": _response(status="failed", has_error=False),
            }
        )
    ]

    with pytest.raises(LlmResponseError) as raised:
        await _collect(OpenAIResponsesProvider(), _target(), _request())

    assert "provider_code" not in raised.value.details


async def test_error_event_with_quota_code_expect_quota_exhausted(
    wire: _Wire,
) -> None:
    """A streamed error event carrying a plan-limit code is a quota failure."""
    wire.replies = [
        _sse(
            {
                "type": "error",
                "code": "subscription_sharing_usage_limit_exceeded",
                "message": "limit",
                "sequence_number": 1,
            }
        )
    ]

    with pytest.raises(LlmQuotaExhaustedError):
        await OpenAIResponsesProvider().complete(_target(), _request())


async def test_sdk_stream_error_payload_expect_error_classified_by_code(
    wire: _Wire,
) -> None:
    """An SSE payload with a nested error object raised by the SDK keeps its code."""
    wire.replies = [
        _sse(
            {
                "type": "error",
                "error": {"code": "insufficient_quota", "message": "spent"},
            }
        )
    ]

    with pytest.raises(LlmQuotaExhaustedError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


async def test_stream_ending_without_terminal_event_expect_interrupted(
    wire: _Wire,
) -> None:
    """A stream that closes before response.completed is never a success."""
    wire.replies = [_sse(_text_delta("partial"))]
    provider = OpenAIResponsesProvider()

    with pytest.raises(LlmStreamInterruptedError) as raised:
        await _collect(provider, _target(), _request())

    assert isinstance(raised.value, LlmTransportError)
    assert raised.value.failure_class is LlmFailureClass.TRANSPORT


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx2.ReadError("dropped"), LlmStreamInterruptedError),
        (httpx2.ReadTimeout("stalled"), LlmTimeoutError),
    ],
)
async def test_connection_failure_mid_stream_expect_typed_error(
    wire: _Wire,
    error: BaseException,
    expected: type[AbstractLlmError],
) -> None:
    """Transport failures after the stream opened are not replayed or swallowed."""
    wire.replies = [
        httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_FailingByteStream(_sse_bytes(_text_delta("partial")), error),
        )
    ]
    received: list[ModelStreamEvent] = []

    with pytest.raises(expected):
        async for event in OpenAIResponsesProvider().stream(_target(), _request()):
            received.append(event)

    assert [event.token_delta for event in received] == ["partial"]
    assert len(wire.requests) == 1


async def test_malformed_sse_payload_expect_response_error(wire: _Wire) -> None:
    """Undecodable SSE data is a response failure, not a crash."""
    wire.replies = [
        httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"event: response.completed\ndata: {not-json\n\n",
        )
    ]

    with pytest.raises(LlmResponseError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (_http_error(401), LlmAuthenticationError),
        (_http_error(408), LlmTimeoutError),
        (_http_error(504), LlmTimeoutError),
        (_http_error(429), LlmRateLimitError),
        (_http_error(429, "insufficient_quota"), LlmQuotaExhaustedError),
        (
            _http_error(429, "subscription_sharing_usage_limit_exceeded"),
            LlmQuotaExhaustedError,
        ),
        (_http_error(500), LlmTransportError),
        (_http_error(400), LlmResponseError),
        (httpx2.ConnectError("refused"), LlmTransportError),
        (httpx2.ConnectTimeout("slow"), LlmTimeoutError),
    ],
)
async def test_http_rejection_expect_typed_error(
    wire: _Wire,
    reply: _Reply,
    expected: type[AbstractLlmError],
) -> None:
    """HTTP and connection failures normalize before any event is produced."""
    wire.replies = [reply]

    with pytest.raises(expected) as raised:
        await OpenAIResponsesProvider().complete(_target(), _request())

    assert type(raised.value) is expected
    assert len(wire.requests) == 1


@pytest.mark.parametrize(
    ("header", "expected"),
    [("7", 7.0), ("soon", None), ("-1", None), ("inf", None), (None, None)],
)
async def test_rate_limit_retry_after_expect_only_valid_seconds(
    wire: _Wire,
    header: str | None,
    expected: float | None,
) -> None:
    """Only a finite non-negative retry-after header becomes a retry hint."""
    headers = {} if header is None else {"retry-after": header}
    wire.replies = [_http_error(429, headers=headers)]

    with pytest.raises(LlmRateLimitError) as raised:
        await OpenAIResponsesProvider().complete(_target(), _request())

    assert raised.value.retry_after_seconds == expected


def test_sdk_error_normalization_expect_validation_and_uncoded_errors() -> None:
    """SDK errors without an HTTP status still map to a typed failure."""
    provider = OpenAIResponsesProvider()
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    validation = APIResponseValidationError(
        response=httpx2.Response(200, request=request),
        body=None,
    )

    assert isinstance(provider._normalized_sdk_error(validation), LlmResponseError)
    assert isinstance(
        provider._normalized_sdk_error(APIError("bad", request, body=None)),
        LlmResponseError,
    )
    assert isinstance(
        provider._normalized_sdk_error(APIConnectionError(request=request)),
        LlmTransportError,
    )
    assert isinstance(
        provider._normalized_sdk_error(
            APIStatusError(
                "busy",
                response=httpx2.Response(503, request=request),
                body=None,
            )
        ),
        LlmTransportError,
    )


async def test_credential_provider_expect_call_time_token(wire: _Wire) -> None:
    """A profile credential provider replaces the static API key per call."""
    wire.replies = [_sse(_text_delta("ok"), _completed())]
    credentials = _RecordingCredentialProvider(["token-1"])
    provider = OpenAIResponsesProvider((credentials,))
    request = _request()
    target = _target(api_key=None, credential_provider="chatgpt")

    await provider.complete(target, request)

    assert wire.bearer() == "Bearer token-1"
    assert credentials.requests == [
        LlmCredentialRequest(
            profile_name="openai-responses",
            request=request,
            rejected_token=None,
        )
    ]


async def test_rejected_credential_expect_one_refresh_and_retry(wire: _Wire) -> None:
    """A 401 hands the rejected token back once and retries with the new one."""
    wire.replies = [_http_error(401, "token_expired"), _sse(_completed())]
    credentials = _RecordingCredentialProvider(["stale", "fresh"])
    provider = OpenAIResponsesProvider((credentials,))

    events = await _collect(
        provider,
        _target(api_key=None, credential_provider="chatgpt"),
        _request(),
    )

    assert events[-1].kind is ModelStreamEventKind.DONE
    assert [wire.bearer(0), wire.bearer(1)] == ["Bearer stale", "Bearer fresh"]
    assert [item.rejected_token for item in credentials.requests] == [None, "stale"]


async def test_credential_rejected_twice_expect_authentication_error(
    wire: _Wire,
) -> None:
    """The retry happens exactly once; a second 401 surfaces as authentication."""
    wire.replies = [_http_error(401), _http_error(401)]
    credentials = _RecordingCredentialProvider(["stale", "fresh"])
    provider = OpenAIResponsesProvider((credentials,))

    with pytest.raises(LlmAuthenticationError):
        await provider.complete(
            _target(api_key=None, credential_provider="chatgpt"),
            _request(),
        )

    assert len(wire.requests) == 2
    assert len(credentials.requests) == 2


async def test_static_key_rejected_expect_no_retry(wire: _Wire) -> None:
    """A rejected static API key is never retried."""
    wire.replies = [_http_error(401)]

    with pytest.raises(LlmAuthenticationError):
        await OpenAIResponsesProvider().complete(_target(), _request())

    assert len(wire.requests) == 1


async def test_unregistered_credential_provider_expect_configuration_error(
    wire: _Wire,
) -> None:
    """A profile naming an unregistered credential provider fails closed."""
    with pytest.raises(LlmConfigurationError):
        await OpenAIResponsesProvider().complete(
            _target(api_key=None, credential_provider="missing"),
            _request(),
        )

    assert wire.requests == []


async def test_blank_credential_token_expect_configuration_error(wire: _Wire) -> None:
    """A blank token from a credential provider is never sent."""
    provider = OpenAIResponsesProvider((_RecordingCredentialProvider([" "]),))

    with pytest.raises(LlmConfigurationError):
        await provider.complete(
            _target(api_key=None, credential_provider="chatgpt"),
            _request(),
        )

    assert wire.requests == []


def test_duplicate_credential_provider_names_expect_configuration_error() -> None:
    """Two credential providers cannot share one profile-facing name."""
    with pytest.raises(LlmConfigurationError):
        OpenAIResponsesProvider(
            (
                _RecordingCredentialProvider(["a"]),
                _RecordingCredentialProvider(["b"]),
            )
        )


async def test_profile_without_any_credential_expect_configuration_error(
    wire: _Wire,
) -> None:
    """A profile with neither API key nor credential provider fails closed."""
    with pytest.raises(LlmConfigurationError):
        await OpenAIResponsesProvider().complete(_target(api_key=None), _request())

    assert wire.requests == []


async def test_foreign_profile_api_expect_unsupported(wire: _Wire) -> None:
    """The adapter refuses profiles that belong to another API family."""
    target = LlmModelTarget(
        model_ref="support/foreign",
        profile_name="foreign",
        profile=LlmProfile(
            provider="openai",
            api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
            api_key=SecretStr("secret"),
        ),
        route=LlmModelRoute(profile="foreign", model="gpt"),
    )

    with pytest.raises(LlmUnsupportedFeatureError):
        await OpenAIResponsesProvider().complete(target, _request())

    assert wire.requests == []


async def test_ambient_custom_headers_expect_configuration_error(
    wire: _Wire,
    monkeypatch: MonkeyPatch,
) -> None:
    """Ambient SDK header injection is rejected like the chat adapter does."""
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "X-Ambient: injected")

    with pytest.raises(LlmConfigurationError):
        await OpenAIResponsesProvider().complete(_target(), _request())

    assert wire.requests == []


async def test_multimodal_user_content_expect_responses_input_parts(
    wire: _Wire,
) -> None:
    """Text, image, and document parts map to Responses input content."""
    wire.replies = [_sse(_text_delta("ok"), _completed())]
    message = ModelMessage.user(
        (
            TextPart("describe"),
            ImagePart.from_uri(
                "https://assets.example.test/chart.png",
                media_type="image/png",
            ),
            ImagePart.from_bytes(b"image", media_type="image/png"),
            DocumentPart.from_bytes(
                b"pdf",
                media_type="application/pdf",
                filename="report.pdf",
            ),
        )
    )

    await OpenAIResponsesProvider().complete(
        _target(input_modalities=frozenset(ModelModality)),
        ModelRequest(messages=(message,)),
    )

    items = cast(Sequence[Mapping[str, object]], wire.body()["input"])
    assert items[0]["content"] == [
        {"type": "input_text", "text": "describe"},
        {
            "type": "input_image",
            "image_url": "https://assets.example.test/chart.png",
            "detail": "auto",
        },
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,aW1hZ2U=",
            "detail": "auto",
        },
        {
            "type": "input_file",
            "file_data": "data:application/pdf;base64,cGRm",
            "filename": "report.pdf",
        },
    ]


async def test_undeclared_input_modality_expect_no_http_call(wire: _Wire) -> None:
    """Media the route did not declare is rejected before any call."""
    request = ModelRequest(
        messages=(
            ModelMessage.user(
                (ImagePart.from_bytes(b"image", media_type="image/png"),)
            ),
        )
    )

    with pytest.raises(LlmUnsupportedFeatureError):
        await _collect(OpenAIResponsesProvider(), _target(), request)

    assert wire.requests == []


@pytest.mark.parametrize(
    "part",
    [
        AudioPart.from_bytes(b"audio", media_type="audio/mpeg"),
        VideoPart.from_bytes(b"video", media_type="video/mp4"),
        ImagePart.from_bytes(b"svg", media_type="image/svg+xml"),
        DocumentPart.from_uri(
            "https://assets.example.test/report.pdf",
            media_type="application/pdf",
            filename="report.pdf",
        ),
        DocumentPart.from_bytes(b"pdf", media_type="application/pdf"),
        DocumentPart.from_bytes(
            b"json",
            media_type="application/json",
            filename="data.json",
        ),
    ],
)
async def test_unsupported_media_representation_expect_no_http_call(
    wire: _Wire,
    part: AudioPart | DocumentPart | ImagePart | VideoPart,
) -> None:
    """Audio, video, and unsupported URI or MIME shapes fail before any call."""
    with pytest.raises(LlmUnsupportedFeatureError):
        await OpenAIResponsesProvider().complete(
            _target(input_modalities=frozenset(ModelModality)),
            ModelRequest(messages=(ModelMessage.user((part,)),)),
        )

    assert wire.requests == []


async def test_assistant_media_history_expect_no_http_call(wire: _Wire) -> None:
    """Assistant media history is not silently reinterpreted as text."""
    message = ModelMessage(
        ModelMessageRole.ASSISTANT,
        (ImagePart.from_bytes(b"image", media_type="image/png"),),
    )

    with pytest.raises(LlmUnsupportedFeatureError):
        await OpenAIResponsesProvider().complete(
            _target(input_modalities=frozenset(ModelModality)),
            ModelRequest(messages=(message,)),
        )

    assert wire.requests == []


def test_corrupted_portable_part_expect_response_error() -> None:
    """Impossible missing-byte and unknown part states remain fail-closed."""
    provider = OpenAIResponsesProvider()
    parts: tuple[ImagePart | DocumentPart, ...] = (
        ImagePart.from_bytes(b"image", media_type="image/png"),
        DocumentPart.from_bytes(
            b"pdf",
            media_type="application/pdf",
            filename="report.pdf",
        ),
    )
    for part in parts:
        object.__setattr__(part, "data", None)
        with pytest.raises(LlmResponseError):
            provider._content_part(part)
    with pytest.raises(LlmResponseError):
        provider._content_part(cast(ModelContentPart, object()))


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"call_id": " "},
        {"call_id": 7},
    ],
)
async def test_tool_message_without_call_id_expect_response_error(
    wire: _Wire,
    metadata: dict[str, JsonValue],
) -> None:
    """A tool result needs the call id that correlates it to its call."""
    message = ModelMessage(ModelMessageRole.TOOL, "result", metadata=metadata)

    with pytest.raises(LlmResponseError):
        await OpenAIResponsesProvider().complete(
            _target(),
            ModelRequest(messages=(message,)),
        )

    assert wire.requests == []


@pytest.mark.parametrize(
    "tool_calls",
    [
        "not-a-sequence",
        7,
        ("not-a-mapping",),
        ({"id": 1, "name": "lookup_weather", "arguments": "{}"},),
        ({"id": "call-1", "name": None, "arguments": "{}"},),
        ({"id": "call-1", "name": "lookup_weather", "arguments": 7},),
    ],
)
async def test_invalid_tool_call_history_expect_response_error(
    wire: _Wire,
    tool_calls: JsonValue,
) -> None:
    """Malformed assistant tool-call history fails before any call."""
    message = ModelMessage(
        ModelMessageRole.ASSISTANT,
        "calling",
        metadata={"tool_calls": tool_calls},
    )

    with pytest.raises(LlmResponseError):
        await OpenAIResponsesProvider().complete(
            _target(),
            ModelRequest(messages=(message,)),
        )

    assert wire.requests == []


def test_empty_tool_list_expect_response_error() -> None:
    """An empty declared tool list is invalid; no tool spec omits the field."""
    request = ModelRequest(messages=(), tool_calling=_tools())
    object.__setattr__(request.tool_calling, "tools", ())

    with pytest.raises(LlmResponseError):
        OpenAIResponsesProvider()._tools(_target(), request)
    assert OpenAIResponsesProvider()._tools(_target(), _request()) is omit


async def test_function_call_done_without_added_expect_call_recovered(
    wire: _Wire,
) -> None:
    """A call announced only by its done item still yields one complete call."""
    wire.replies = [
        _sse(
            _item_event("done", {"type": "message", "id": "msg-1", "content": []}),
            _item_event("done", _function_item('{"city":"Jeju"}')),
            _completed(),
        )
    ]

    events = await _collect(
        OpenAIResponsesProvider(),
        _target(),
        _request(tool_calling=_tools()),
    )

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOOL_CALL_START,
        ModelStreamEventKind.TOOL_CALL_END,
        ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        ModelStreamEventKind.DONE,
    ]
    candidate = events[2].tool_call
    assert candidate is not None
    assert candidate.arguments == {"city": "Jeju"}


async def test_argument_delta_for_unknown_call_expect_response_error(
    wire: _Wire,
) -> None:
    """Argument text for a call that was never announced is invalid."""
    wire.replies = [_sse(_arguments_delta("{}"), _completed())]

    with pytest.raises(LlmResponseError):
        await _collect(
            OpenAIResponsesProvider(),
            _target(),
            _request(tool_calling=_tools()),
        )


async def test_provider_native_tool_item_expect_unsupported(wire: _Wire) -> None:
    """Provider-executed tool items are never treated as agent tool calls."""
    wire.replies = [
        _sse(
            _item_event(
                "added",
                {"type": "web_search_call", "id": "ws-1", "status": "in_progress"},
            ),
            _completed(),
        )
    ]

    with pytest.raises(LlmUnsupportedFeatureError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


async def test_function_call_without_declared_tools_expect_response_error(
    wire: _Wire,
) -> None:
    """A function call without caller-declared tools has no authority."""
    wire.replies = [_sse(_item_event("added", _function_item()), _completed())]

    with pytest.raises(LlmResponseError):
        await _collect(OpenAIResponsesProvider(), _target(), _request())


async def test_required_tool_choice_without_call_expect_response_error(
    wire: _Wire,
) -> None:
    """A required tool choice that produced no call is a response failure."""
    wire.replies = [_sse(_text_delta("no call"), _completed())]

    with pytest.raises(LlmResponseError):
        await OpenAIResponsesProvider().complete(
            _target(),
            _request(tool_calling=_tools(ModelToolChoice.REQUIRED)),
        )


async def test_function_call_with_undeclared_arguments_expect_response_error(
    wire: _Wire,
) -> None:
    """Tool arguments are validated against the declared parameter schema."""
    wire.replies = [
        _sse(
            _item_event("added", _function_item()),
            _item_event("done", _function_item('{"town":"Seoul"}')),
            _completed(),
        )
    ]

    with pytest.raises(LlmResponseError):
        await OpenAIResponsesProvider().complete(
            _target(),
            _request(tool_calling=_tools()),
        )


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (LlmQuotaExhaustedError(), "llm_quota_exhausted", False),
        (LlmAuthenticationError(), "llm_authentication_failed", False),
        (LlmStreamInterruptedError(), "llm_stream_interrupted", True),
    ],
)
def test_new_failures_expect_stable_public_codes(
    error: AbstractLlmError,
    code: str,
    retryable: bool,
) -> None:
    """Quota is reported as non-retryable, unlike a transient rate limit."""
    model_error = to_model_error(error, _target())

    assert failure_code(error) == code
    assert model_error.code == code
    assert model_error.retryable is retryable
    assert to_model_error(LlmRateLimitError(), _target()).retryable is True
