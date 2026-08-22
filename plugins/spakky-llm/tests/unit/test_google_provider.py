"""Tests for the native Google Gemini GenerateContent provider."""

from base64 import b64encode
from collections.abc import AsyncIterator
from typing import override
from unittest.mock import patch

import httpx
import pytest
from google.auth.credentials import AnonymousCredentials
from google.auth.exceptions import (
    DefaultCredentialsError,
    RefreshError,
    TransportError as GoogleAuthTransportError,
)
from google.genai import errors, types
from pydantic import SecretStr
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunner,
    AgentYieldKind,
    IAgentModel,
    Idempotency,
    JsonObject,
    JsonSchemaConstraint,
    KeepRecentMessagesCompactionStrategy,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelToolCall,
    ModelToolSpec,
    ModelUsage,
    SamplingOptions,
    RunAgentInput,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)

from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
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
from spakky.plugins.llm.provider import LlmModelTarget
from spakky.plugins.llm.providers.google import GoogleGenerateContentProvider


async def test_compacted_tool_group_maps_to_complete_google_native_history() -> None:
    """KeepRecent(max_messages=1) preserves Google function call/response pairs."""
    group = (
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "",
            metadata={
                "tool_calls": (
                    {"id": "call-1", "name": "search", "arguments": {"q": "x"}},
                )
            },
        ),
        ModelMessage(
            ModelMessageRole.TOOL,
            "result",
            metadata={"call_id": "call-1", "tool_name": "search"},
        ),
    )
    compacted = await KeepRecentMessagesCompactionStrategy(max_messages=1).compact(
        (ModelMessage(ModelMessageRole.USER, "old"), *group),
        ModelUsage(),
        ModelCapability(),
    )

    native = GoogleGenerateContentProvider()._contents(ModelRequest(messages=compacted))

    assert [content.role for content in native] == ["model", "user"]
    assert native[0].parts is not None
    assert native[0].parts[0].function_call is not None
    assert native[0].parts[0].function_call.id == "call-1"
    assert native[1].parts is not None
    assert native[1].parts[0].function_response is not None
    assert native[1].parts[0].function_response.id == "call-1"


class _RecordingModels:
    """Record SDK calls while returning deterministic typed responses."""

    def __init__(
        self,
        response: types.GenerateContentResponse | None = None,
        chunks: tuple[types.GenerateContentResponse, ...] = (),
        *,
        complete_error: Exception | None = None,
        stream_start_error: Exception | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.response = response or _text_response("ok")
        self.chunks = chunks
        self.complete_error = complete_error
        self.stream_start_error = stream_start_error
        self.stream_error = stream_error
        self.model: str | None = None
        self.contents: types.ContentListUnion | types.ContentListUnionDict | None = None
        self.config: types.GenerateContentConfigOrDict | None = None

    async def generate_content(
        self,
        *,
        model: str,
        contents: types.ContentListUnion | types.ContentListUnionDict,
        config: types.GenerateContentConfigOrDict | None = None,
    ) -> types.GenerateContentResponse:
        self.model = model
        self.contents = contents
        self.config = config
        if self.complete_error is not None:
            raise self.complete_error
        return self.response

    async def generate_content_stream(
        self,
        *,
        model: str,
        contents: types.ContentListUnion | types.ContentListUnionDict,
        config: types.GenerateContentConfigOrDict | None = None,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        self.model = model
        self.contents = contents
        self.config = config
        if self.stream_start_error is not None:
            raise self.stream_start_error
        return self._iterate_chunks()

    async def _iterate_chunks(self) -> AsyncIterator[types.GenerateContentResponse]:
        for chunk in self.chunks:
            yield chunk
        if self.stream_error is not None:
            raise self.stream_error


class _RecordingAsyncClient:
    """Async context manager exposing the recording models module."""

    def __init__(self, models: _RecordingModels) -> None:
        self.models = models
        self.entered = False
        self.closed = False

    async def __aenter__(self) -> "_RecordingAsyncClient":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


class _RecordingClient:
    """Minimal official-client shape used by the provider."""

    def __init__(self, models: _RecordingModels) -> None:
        self.aio = _RecordingAsyncClient(models)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _target(
    *,
    api_key: str | None = "google-key",
    include_thoughts: bool = False,
    max_retries: int = 2,
    base_url: str | None = "https://gemini.example.test",
    api: LlmProviderApi = LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
    credential_strategy: GoogleCredentialStrategy | None = None,
    project: str | None = None,
    location: str | None = None,
    service_account_file: str | None = None,
) -> LlmModelTarget:
    strategy = credential_strategy
    if strategy is None and api == LlmProviderApi.GOOGLE_GEMINI_DEVELOPER:
        strategy = GoogleCredentialStrategy.API_KEY
    if strategy is None and api == LlmProviderApi.GOOGLE_VERTEX:
        strategy = GoogleCredentialStrategy.ADC
    profile = LlmProfile.model_construct(
        provider="google",
        api=api,
        base_url=base_url,
        api_key=SecretStr(api_key) if api_key is not None else None,
        headers={"x-tenant": "spakky"},
        request_timeout_seconds=12.5,
        stream_timeout_seconds=45.0,
        max_retries=max_retries,
        stream_enabled=True,
        google_credential_strategy=strategy,
        google_project=project,
        google_location=location,
        google_service_account_file=service_account_file,
    )
    profile_name = (
        "google-vertex" if api == LlmProviderApi.GOOGLE_VERTEX else "google-developer"
    )
    return LlmModelTarget(
        model_ref="support/primary",
        profile_name=profile_name,
        profile=profile,
        route=LlmModelRoute(
            profile=profile_name,
            model="gemini-2.5-pro",
            capability=ModelCapability(supports_reasoning=include_thoughts),
        ),
    )


def _request(
    *,
    messages: tuple[ModelMessage, ...] | None = None,
    tool_calling: ToolCallingSpec | None = None,
    structured_output: StructuredOutputSpec | None = None,
    include_usage: bool = True,
) -> ModelRequest:
    return ModelRequest(
        messages=messages or (ModelMessage(ModelMessageRole.USER, "hello Gemini"),),
        tool_calling=tool_calling,
        structured_output=structured_output,
        sampling=SamplingOptions(temperature=0.2, top_p=0.8, max_tokens=512),
        streaming=StreamingOptions(include_usage=include_usage),
    )


def _tool_calling(
    choice: ModelToolChoice = ModelToolChoice.AUTO,
) -> ToolCallingSpec:
    return ToolCallingSpec(
        tools=(
            ModelToolSpec(
                name="search",
                description="Search documents",
                parameters=JsonSchemaConstraint(
                    schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    }
                ),
            ),
        ),
        choice=choice,
    )


def _structured_output() -> StructuredOutputSpec:
    return StructuredOutputSpec(
        constraint=JsonSchemaConstraint(
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            }
        ),
        output_type_name="Answer",
    )


def _text_response(
    text: str,
    *,
    finish_reason: types.FinishReason | None = types.FinishReason.STOP,
    usage: types.GenerateContentResponseUsageMetadata | None = None,
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=text)],
                ),
                finish_reason=finish_reason,
            )
        ],
        usage_metadata=usage,
    )


async def _collect(
    provider: GoogleGenerateContentProvider,
    target: LlmModelTarget,
    request: ModelRequest,
) -> list[ModelStreamEvent]:
    return [event async for event in provider.stream(target, request)]


def test_api_expect_google_generate_content_family() -> None:
    """Provider registry key is the native Google GenerateContent API."""
    provider = GoogleGenerateContentProvider()

    assert provider.apis == frozenset(
        {
            LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
            LlmProviderApi.GOOGLE_VERTEX,
        }
    )


@pytest.mark.parametrize("operation", ["complete", "stream"])
async def test_max_tokens_is_an_explicit_success_terminal(operation: str) -> None:
    """A token-budget terminal remains usable when no stricter schema is requested."""
    response = _text_response(
        "partial",
        finish_reason=types.FinishReason.MAX_TOKENS,
    )
    models = (
        _RecordingModels(response)
        if operation == "complete"
        else _RecordingModels(chunks=(response,))
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(models),
    ):
        if operation == "complete":
            result = await GoogleGenerateContentProvider().complete(
                _target(),
                _request(),
            )
            assert result.metadata["finish_reason"] == "MAX_TOKENS"
        else:
            events = await _collect(
                GoogleGenerateContentProvider(),
                _target(),
                _request(),
            )
            assert events[-1].metadata["finish_reason"] == "MAX_TOKENS"


async def test_complete_maps_native_request_response_and_metadata() -> None:
    """Complete preserves native roles, tools, schemas, usage, and profile metadata."""
    call_signature = b"call-signature"
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="internal", thought=True),
                        types.Part.from_text(text='{"answer":"ok"}'),
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call-2",
                                name="search",
                                args={"query": "spakky", "tags": ["agent"]},
                            ),
                            thought_signature=call_signature,
                        ),
                    ],
                ),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=11,
            candidates_token_count=7,
            thoughts_token_count=3,
            total_token_count=21,
        ),
    )
    models = _RecordingModels(response)
    client = _RecordingClient(models)
    prior_signature = b64encode(b"prior-signature").decode("ascii")
    request = _request(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "Be concise"),
            ModelMessage(ModelMessageRole.USER, "Find it"),
            ModelMessage(
                ModelMessageRole.ASSISTANT,
                "Calling lookup",
                metadata={
                    "thought_signature": prior_signature,
                    "tool_calls": (
                        {
                            "id": "call-1",
                            "name": "lookup",
                            "arguments": {"query": "old"},
                            "thought_signature": prior_signature,
                        },
                    ),
                },
            ),
            ModelMessage(
                ModelMessageRole.TOOL,
                "lookup result",
                metadata={"tool_name": "lookup", "call_id": "call-1"},
            ),
            ModelMessage(ModelMessageRole.EVIDENCE, "trusted evidence"),
        ),
        tool_calling=_tool_calling(ModelToolChoice.REQUIRED),
        structured_output=_structured_output(),
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=client,
    ) as client_factory:
        result = await GoogleGenerateContentProvider().complete(_target(), request)

    assert result.content == '{"answer":"ok"}'
    assert result.structured_output == {"answer": "ok"}
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 21
    assert result.metadata == {
        "model_ref": "support/primary",
        "provider": "google",
        "profile": "google-developer",
        "model": "gemini-2.5-pro",
        "finish_reason": "STOP",
    }
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].call_id == "call-2"
    assert result.tool_calls[0].arguments == {
        "query": "spakky",
        "tags": ("agent",),
    }
    assert result.tool_calls[0].metadata == {
        "model_ref": "support/primary",
        "provider": "google",
        "profile": "google-developer",
        "model": "gemini-2.5-pro",
        "thought_signature": b64encode(call_signature).decode("ascii"),
    }
    assert client.aio.entered is True
    assert client.aio.closed is True

    assert client.closed is True
    assert models.model == "gemini-2.5-pro"
    assert isinstance(models.contents, list)
    assert len(models.contents) == 4
    user_content, assistant_content, tool_content, evidence_content = models.contents
    assert isinstance(user_content, types.Content)
    assert user_content.role == "user"
    assert isinstance(assistant_content, types.Content)
    assert assistant_content.role == "model"
    assert assistant_content.parts is not None
    assert assistant_content.parts[0].thought_signature == b"prior-signature"
    assert assistant_content.parts[1].function_call is not None
    assert assistant_content.parts[1].function_call.id == "call-1"
    assert assistant_content.parts[1].thought_signature == b"prior-signature"
    assert isinstance(tool_content, types.Content)
    assert tool_content.role == "user"
    assert tool_content.parts is not None
    assert tool_content.parts[0].function_response is not None
    assert tool_content.parts[0].function_response.id == "call-1"
    assert tool_content.parts[0].function_response.name == "lookup"
    assert isinstance(evidence_content, types.Content)
    assert evidence_content.role == "user"
    assert evidence_content.parts is not None
    assert evidence_content.parts[0].text == "trusted evidence"
    assert isinstance(models.config, types.GenerateContentConfig)
    assert isinstance(models.config.system_instruction, types.Content)
    assert models.config.system_instruction.parts is not None
    assert models.config.system_instruction.parts[0].text == "Be concise"
    assert models.config.temperature == 0.2
    assert models.config.top_p == 0.8
    assert models.config.max_output_tokens == 512
    assert models.config.response_mime_type == "application/json"
    assert models.config.response_json_schema == _structured_output().constraint.schema
    assert models.config.automatic_function_calling is not None
    assert models.config.automatic_function_calling.disable is True
    assert models.config.tool_config is not None
    assert models.config.tool_config.function_calling_config is not None
    assert (
        models.config.tool_config.function_calling_config.mode
        is types.FunctionCallingConfigMode.ANY
    )
    assert models.config.tools is not None
    assert isinstance(models.config.tools[0], types.Tool)
    assert models.config.tools[0].function_declarations is not None
    declaration = models.config.tools[0].function_declarations[0]
    assert declaration.name == "search"
    assert declaration.description == "Search documents"
    assert (
        declaration.parameters_json_schema == _tool_calling().tools[0].parameters.schema
    )
    client_factory.assert_called_once()
    client_kwargs = client_factory.call_args.kwargs
    assert client_kwargs["api_key"] == "google-key"
    assert client_kwargs["enterprise"] is False
    http_options = client_kwargs["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.base_url == "https://gemini.example.test"
    assert http_options.headers == {"x-tenant": "spakky"}
    assert http_options.timeout == 12_500
    assert http_options.async_client_args is not None
    assert isinstance(
        http_options.async_client_args["transport"],
        httpx.AsyncHTTPTransport,
    )
    assert http_options.retry_options is not None
    assert http_options.retry_options.attempts == 3


class _RoundTripGoogleModel(IAgentModel):
    """Runner-facing Google probe that inspects the next native request parts."""

    def __init__(self, signature: str) -> None:
        self.signature = signature
        self.requests: list[ModelRequest] = []
        self.restored_signature: bytes | None = None
        self.provider = GoogleGenerateContentProvider()

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_tools=True)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        if len(self.requests) == 1:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=ModelToolCall(
                    name="search",
                    arguments={"query": "spakky"},
                    call_id="google-call-1",
                    metadata={"thought_signature": self.signature},
                ),
            )
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        contents = self.provider._contents(request)
        assistant = next(content for content in contents if content.role == "model")
        assert assistant.parts is not None
        tool_part = next(
            part for part in assistant.parts if part.function_call is not None
        )
        self.restored_signature = tool_part.thought_signature
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="grounded",
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Agent(spec=AgentExecutionSpec(name="google_round_trip"))
class _GoogleRoundTripAgent:
    """Stateless tool agent used for Google thought-signature continuation."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="search",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def search(self, query: str) -> str:
        return f"result:{query}"


async def test_runner_google_thought_signature_round_trips_to_next_native_part() -> (
    None
):
    """Runner assistant history restores Google thought_signature on the next request."""
    signature_bytes = b"google-round-trip-signature"
    signature = b64encode(signature_bytes).decode("ascii")
    model = _RoundTripGoogleModel(signature)
    runner = AgentRunner.for_agent_instance(_GoogleRoundTripAgent(model))

    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="google-round-trip", instruction="search")
        )
    ]

    assert model.restored_signature == signature_bytes
    assert len(model.requests) == 2
    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 1


async def test_google_profile_fences_ambient_vertex_and_endpoint(monkeypatch) -> None:
    """Ambient Google mode cannot redirect a Developer API profile to Vertex."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "ambient-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "ambient-location")
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-gemini-key")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://ambient.invalid/")
    monkeypatch.setenv("GOOGLE_VERTEX_BASE_URL", "https://ambient-vertex.invalid/")

    client = GoogleGenerateContentProvider()._client(
        _target(base_url=None),
        timeout_seconds=12.5,
    )
    try:
        assert client.vertexai is False
        assert client._api_client.api_key == "google-key"
        assert (
            client._api_client._http_options.base_url
            == "https://generativelanguage.googleapis.com/"
        )
        assert client._api_client._use_aiohttp() is False
    finally:
        await client.aio.aclose()
        client.close()


def test_vertex_adc_uses_only_explicit_mode_coordinates_and_selected_credentials(
    monkeypatch,
) -> None:
    """Explicit ADC selection ignores ambient backend/project/location routing values."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "false")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "ambient-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "ambient-location")
    monkeypatch.setenv("GOOGLE_API_KEY", "ambient-key")
    credentials = AnonymousCredentials()
    client = _RecordingClient(_RecordingModels())
    target = _target(
        api=LlmProviderApi.GOOGLE_VERTEX,
        api_key=None,
        base_url=None,
        project="configured-project",
        location="us-central1",
    )

    with (
        patch(
            "spakky.plugins.llm.providers.google.google.auth.default",
            return_value=(credentials, "ambient-discovered-project"),
        ) as adc,
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=client,
        ) as constructor,
    ):
        result = GoogleGenerateContentProvider()._client(
            target,
            timeout_seconds=12.5,
        )

    assert result is client
    adc.assert_called_once_with(
        scopes=("https://www.googleapis.com/auth/cloud-platform",)
    )
    kwargs = constructor.call_args.kwargs
    assert kwargs["enterprise"] is True
    assert kwargs["credentials"] is credentials
    assert kwargs["project"] == "configured-project"
    assert kwargs["location"] == "us-central1"
    assert "api_key" not in kwargs
    http_options = kwargs["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.base_url == "https://us-central1-aiplatform.googleapis.com/"


def test_vertex_service_account_loads_only_configured_file() -> None:
    """Service-account strategy never falls back to ADC or an ambient credential path."""
    credentials = AnonymousCredentials()
    client = _RecordingClient(_RecordingModels())
    target = _target(
        api=LlmProviderApi.GOOGLE_VERTEX,
        api_key=None,
        base_url=None,
        credential_strategy=GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE,
        project="configured-project",
        location="europe-west4",
        service_account_file="/mounted/configured-service-account.json",
    )

    with (
        patch("spakky.plugins.llm.providers.google.google.auth.default") as adc,
        patch(
            "spakky.plugins.llm.providers.google.service_account.Credentials.from_service_account_file",
            return_value=credentials,
        ) as loader,
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=client,
        ) as constructor,
    ):
        result = GoogleGenerateContentProvider()._client(
            target,
            timeout_seconds=45.0,
        )

    assert result is client
    adc.assert_not_called()
    loader.assert_called_once_with(
        "/mounted/configured-service-account.json",
        scopes=("https://www.googleapis.com/auth/cloud-platform",),
    )
    kwargs = constructor.call_args.kwargs
    assert kwargs["enterprise"] is True
    assert kwargs["credentials"] is credentials
    assert kwargs["project"] == "configured-project"
    assert kwargs["location"] == "europe-west4"
    http_options = kwargs["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.base_url == "https://europe-west4-aiplatform.googleapis.com/"


@pytest.mark.parametrize(
    ("location", "expected_base_url"),
    [
        ("global", "https://aiplatform.googleapis.com/"),
        ("us", "https://aiplatform.us.rep.googleapis.com/"),
        ("eu", "https://aiplatform.eu.rep.googleapis.com/"),
        ("asia-northeast3", "https://asia-northeast3-aiplatform.googleapis.com/"),
    ],
)
async def test_vertex_endpoint_is_explicit_and_ambient_base_url_cannot_override(
    monkeypatch,
    location: str,
    expected_base_url: str,
) -> None:
    """Regional/global Vertex endpoints are explicit before SDK env resolution."""
    monkeypatch.setenv("GOOGLE_VERTEX_BASE_URL", "https://ambient.invalid/")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://ambient-gemini.invalid/")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "ambient-location")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "ambient-project")
    credentials = AnonymousCredentials()
    target = _target(
        api=LlmProviderApi.GOOGLE_VERTEX,
        api_key=None,
        base_url=None,
        project="configured-project",
        location=location,
    )

    with patch(
        "spakky.plugins.llm.providers.google.google.auth.default",
        return_value=(credentials, "ambient-project"),
    ):
        client = GoogleGenerateContentProvider()._client(
            target,
            timeout_seconds=12.5,
        )
    try:
        assert client.vertexai is True
        assert client._api_client._http_options.base_url == expected_base_url
    finally:
        await client.aio.aclose()
        client.close()


def test_vertex_custom_base_url_wins_over_official_endpoint() -> None:
    """Operator-owned custom Vertex endpoint remains higher priority than location."""
    profile = _target(
        api=LlmProviderApi.GOOGLE_VERTEX,
        api_key=None,
        base_url="https://vertex-proxy.example/v1",
        project="configured-project",
        location="us-central1",
    ).profile

    options = GoogleGenerateContentProvider()._http_options(profile, 12.5)

    assert options.base_url == "https://vertex-proxy.example/v1"


@pytest.mark.parametrize("location", [None, "us-central1/evil"])
def test_vertex_endpoint_defensively_rejects_unsafe_constructed_locations(
    location: str | None,
) -> None:
    """Bypassed profile validation cannot inject a Vertex endpoint hostname."""
    with pytest.raises(LlmConfigurationError):
        GoogleGenerateContentProvider()._vertex_base_url(location)


@pytest.mark.parametrize(
    "credential_error",
    [
        DefaultCredentialsError("missing ADC"),
        OSError("unreadable service account"),
        ValueError("malformed service account"),
    ],
)
def test_vertex_credential_loading_failures_are_configuration_errors(
    credential_error: Exception,
) -> None:
    """ADC/file discovery and parse errors never escape the plugin error boundary."""
    provider = GoogleGenerateContentProvider()
    if isinstance(credential_error, DefaultCredentialsError):
        target = _target(
            api=LlmProviderApi.GOOGLE_VERTEX,
            api_key=None,
            project="configured-project",
            location="us-central1",
        )
        patcher = patch(
            "spakky.plugins.llm.providers.google.google.auth.default",
            side_effect=credential_error,
        )
    else:
        target = _target(
            api=LlmProviderApi.GOOGLE_VERTEX,
            api_key=None,
            credential_strategy=GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE,
            project="configured-project",
            location="us-central1",
            service_account_file="/mounted/google.json",
        )
        patcher = patch(
            "spakky.plugins.llm.providers.google.service_account.Credentials.from_service_account_file",
            side_effect=credential_error,
        )

    with patcher, pytest.raises(LlmConfigurationError):
        provider._client(target, timeout_seconds=12.5)


@pytest.mark.parametrize(
    ("strategy", "service_account_file"),
    [
        (GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE, None),
        (GoogleCredentialStrategy.API_KEY, None),
    ],
)
def test_vertex_credentials_defensively_reject_invalid_constructed_profiles(
    strategy: GoogleCredentialStrategy,
    service_account_file: str | None,
) -> None:
    """Bypassed profile validation cannot trigger credential fallback."""
    profile = LlmProfile.model_construct(
        provider="google",
        api=LlmProviderApi.GOOGLE_VERTEX,
        google_credential_strategy=strategy,
        google_project="configured-project",
        google_location="us-central1",
        google_service_account_file=service_account_file,
    )

    with pytest.raises(LlmConfigurationError):
        GoogleGenerateContentProvider()._vertex_credentials(profile)


@pytest.mark.parametrize(
    ("auth_error", "expected_error"),
    [
        (GoogleAuthTransportError("offline"), LlmTransportError),
        (RefreshError("invalid credential"), LlmConfigurationError),
    ],
)
@pytest.mark.parametrize("operation", ["complete", "stream"])
async def test_google_auth_request_failures_are_normalized(
    auth_error: Exception,
    expected_error: type[AbstractLlmError],
    operation: str,
) -> None:
    """Credential refresh and transport failures stay in the typed LLM boundary."""
    models = (
        _RecordingModels(complete_error=auth_error)
        if operation == "complete"
        else _RecordingModels(stream_start_error=auth_error)
    )

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ),
        pytest.raises(expected_error),
    ):
        if operation == "complete":
            await GoogleGenerateContentProvider().complete(_target(), _request())
        else:
            await _collect(GoogleGenerateContentProvider(), _target(), _request())


def test_google_provider_rejects_foreign_api_profiles() -> None:
    """Direct provider resolution cannot bypass the API adapter allowlist."""
    with pytest.raises(LlmProviderUnavailableError):
        GoogleGenerateContentProvider()._client(
            _target(api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            timeout_seconds=12.5,
        )


async def test_complete_maps_plain_assistant_as_model_text() -> None:
    """A plain assistant message retains its text under Gemini's model role."""
    models = _RecordingModels()
    request = _request(
        messages=(ModelMessage(ModelMessageRole.ASSISTANT, "previous answer"),)
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(models),
    ):
        result = await GoogleGenerateContentProvider().complete(_target(), request)

    assert result.content == "ok"
    assert result.usage.input_tokens is None
    assert isinstance(models.contents, list)
    assert len(models.contents) == 1
    assistant = models.contents[0]
    assert isinstance(assistant, types.Content)
    assert assistant.role == "model"
    assert assistant.parts is not None
    assert assistant.parts[0].text == "previous answer"
    assert isinstance(models.config, types.GenerateContentConfig)
    assert models.config.system_instruction is None
    assert models.config.tools is None
    assert models.config.tool_config is None
    assert models.config.automatic_function_calling is None
    assert models.config.thinking_config is None
    assert models.config.response_json_schema is None


async def test_complete_rejects_tool_message_without_name() -> None:
    """A TOOL message cannot silently degrade to ordinary user text."""
    request = _request(
        messages=(ModelMessage(ModelMessageRole.TOOL, "untyped result"),)
    )

    with pytest.raises(LlmResponseError):
        await GoogleGenerateContentProvider().complete(_target(), request)


async def test_complete_replays_assistant_tool_call_without_text() -> None:
    """A prior model tool call remains a function part when assistant text is empty."""
    models = _RecordingModels()
    request = _request(
        messages=(
            ModelMessage(
                ModelMessageRole.ASSISTANT,
                "",
                metadata={
                    "tool_calls": (
                        {"id": "prior-1", "name": "search", "arguments": {}},
                    )
                },
            ),
        )
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(models),
    ):
        await GoogleGenerateContentProvider().complete(_target(), request)

    assert isinstance(models.contents, list)
    content = models.contents[0]
    assert isinstance(content, types.Content)
    assert content.parts is not None
    assert len(content.parts) == 1
    assert content.parts[0].function_call is not None
    assert content.parts[0].function_call.id == "prior-1"


@pytest.mark.parametrize(
    "metadata",
    [
        {"tool_calls": "bad"},
        {"tool_calls": ("bad",)},
        {"tool_calls": ({"arguments": {}},)},
        {"tool_calls": ({"name": "search", "arguments": "bad"},)},
        {"tool_calls": ({"name": "search", "id": ""},)},
        {"thought_signature": 3},
        {"thought_signature": "%%%"},
    ],
)
async def test_complete_rejects_malformed_assistant_metadata(
    metadata: JsonObject,
) -> None:
    """Malformed replay metadata fails before any provider request is sent."""
    models = _RecordingModels()
    request = _request(
        messages=(ModelMessage(ModelMessageRole.ASSISTANT, "prior", metadata),)
    )

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ) as client_factory,
        pytest.raises(LlmResponseError),
    ):
        await GoogleGenerateContentProvider().complete(_target(), request)

    client_factory.assert_not_called()


async def test_complete_rejects_blank_tool_response_metadata() -> None:
    """Present tool correlation metadata must be non-blank."""
    request = _request(
        messages=(
            ModelMessage(
                ModelMessageRole.TOOL,
                "result",
                metadata={"tool_name": "search", "call_id": ""},
            ),
        )
    )

    with pytest.raises(LlmResponseError):
        await GoogleGenerateContentProvider().complete(_target(), request)


async def test_complete_requires_api_key_and_normalizes_client_configuration() -> None:
    """Missing or SDK-rejected client configuration becomes a typed config error."""
    provider = GoogleGenerateContentProvider()

    with pytest.raises(LlmConfigurationError):
        await provider.complete(_target(api_key=None), _request())

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            side_effect=ValueError("invalid options"),
        ),
        pytest.raises(LlmConfigurationError),
    ):
        await provider.complete(_target(), _request())


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (errors.ClientError(408, {"message": "timeout"}), LlmTimeoutError),
        (
            errors.ClientError(429, {"message": "rate limited"}),
            LlmTransportError,
        ),
        (
            errors.ServerError(503, {"message": "unavailable"}),
            LlmTransportError,
        ),
        (errors.ClientError(400, {"message": "bad request"}), LlmResponseError),
    ],
)
async def test_complete_normalizes_google_api_errors(
    provider_error: errors.APIError,
    expected_error: type[AbstractLlmError],
) -> None:
    """Google HTTP error classes map to stable plugin error families."""
    models = _RecordingModels(complete_error=provider_error)

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ),
        pytest.raises(expected_error),
    ):
        await GoogleGenerateContentProvider().complete(_target(), _request())


@pytest.mark.parametrize(
    ("transport_error", "expected_error"),
    [
        (httpx.ReadTimeout("slow"), LlmTimeoutError),
        (httpx.ConnectError("offline"), LlmTransportError),
    ],
)
async def test_complete_normalizes_httpx_transport_errors(
    transport_error: httpx.HTTPError,
    expected_error: type[AbstractLlmError],
) -> None:
    """Default SDK httpx timeout and network failures do not leak outward."""
    models = _RecordingModels(complete_error=transport_error)

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ),
        pytest.raises(expected_error),
    ):
        await GoogleGenerateContentProvider().complete(_target(), _request())


@pytest.mark.parametrize(
    ("operation", "transport_error", "expected_error"),
    [
        ("complete", httpx.ReadTimeout("slow"), LlmTimeoutError),
        ("complete", httpx.ConnectError("offline"), LlmTransportError),
        ("stream", httpx.ReadTimeout("slow"), LlmTimeoutError),
        ("stream", httpx.ConnectError("offline"), LlmTransportError),
    ],
)
async def test_installed_google_sdk_uses_owned_httpx_transport(
    operation: str,
    transport_error: httpx.HTTPError,
    expected_error: type[AbstractLlmError],
) -> None:
    """The installed SDK uses the injected httpx transport for every async call."""

    async def fail_request(_: httpx.Request) -> httpx.Response:
        raise transport_error

    transport = httpx.MockTransport(fail_request)
    provider = GoogleGenerateContentProvider()
    target = _target(max_retries=0)

    with (
        patch(
            "spakky.plugins.llm.providers.google.httpx.AsyncHTTPTransport",
            return_value=transport,
        ),
        pytest.raises(expected_error),
    ):
        if operation == "complete":
            await provider.complete(target, _request())
        else:
            await _collect(provider, target, _request())


@pytest.mark.parametrize("operation", ["complete", "stream"])
@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({"content-type": "application/json"}, b"not-json"),
        ({"content-type": "application/json"}, b'{"candidates":[1]}'),
        (
            {"content-type": "application/json"},
            b'{"candidates":[{"content":5}]}',
        ),
        (
            {"content-type": "application/json"},
            b'{"usageMetadata":{"totalTokenCount":"invalid"}}',
        ),
        (
            {
                "content-encoding": "gzip",
                "content-type": "application/json",
            },
            b"not-gzip",
        ),
    ],
)
async def test_installed_google_sdk_rejects_malformed_success_payloads(
    operation: str,
    headers: dict[str, str],
    body: bytes,
) -> None:
    """SDK decode and validation errors stay inside the generic response boundary."""

    async def malformed_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=body, request=request)

    transport = httpx.MockTransport(malformed_response)
    provider = GoogleGenerateContentProvider()
    target = _target(max_retries=0)

    with (
        patch(
            "spakky.plugins.llm.providers.google.httpx.AsyncHTTPTransport",
            return_value=transport,
        ),
        pytest.raises(LlmResponseError),
    ):
        if operation == "complete":
            await provider.complete(target, _request())
        else:
            await _collect(provider, target, _request())


@pytest.mark.parametrize("operation", ["complete", "stream"])
async def test_google_invalid_url_never_escapes_as_an_sdk_error(operation: str) -> None:
    """Malformed allowlisted endpoints fail through the stable configuration boundary."""
    provider = GoogleGenerateContentProvider()
    target = _target(base_url="://", max_retries=0)

    with pytest.raises(LlmConfigurationError):
        if operation == "complete":
            await provider.complete(target, _request())
        else:
            await _collect(provider, target, _request())


@pytest.mark.parametrize(
    "response",
    [
        types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY
            )
        ),
        _text_response("blocked", finish_reason=types.FinishReason.SAFETY),
        _text_response("blocked", finish_reason=types.FinishReason.LANGUAGE),
        _text_response("blocked", finish_reason=types.FinishReason.NO_IMAGE),
    ],
)
async def test_complete_rejects_google_refusal_signals(
    response: types.GenerateContentResponse,
) -> None:
    """Prompt blocks and safety finish reasons become model refusals."""
    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(response)),
        ),
        pytest.raises(LlmModelRefusalError),
    ):
        await GoogleGenerateContentProvider().complete(_target(), _request())


@pytest.mark.parametrize(
    "response",
    [
        types.GenerateContentResponse(),
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[]))]
        ),
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=None,
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=None),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
        _text_response(
            "bad call",
            finish_reason=types.FinishReason.MALFORMED_FUNCTION_CALL,
        ),
        _text_response(
            "unspecified",
            finish_reason=types.FinishReason.FINISH_REASON_UNSPECIFIED,
        ),
        _text_response("other", finish_reason=types.FinishReason.OTHER),
        _text_response("image other", finish_reason=types.FinishReason.IMAGE_OTHER),
    ],
)
async def test_complete_rejects_invalid_google_responses(
    response: types.GenerateContentResponse,
) -> None:
    """Missing candidates, empty content, and malformed calls fail closed."""
    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(response)),
        ),
        pytest.raises(LlmResponseError),
    ):
        await GoogleGenerateContentProvider().complete(_target(), _request())


async def test_complete_validates_tool_choice_name_and_arguments() -> None:
    """Native tool candidates must be declared, named, schema-valid, and allowed."""
    cases = (
        (
            types.Part(function_call=types.FunctionCall(args={})),
            _tool_calling(),
        ),
        (
            types.Part(function_call=types.FunctionCall(name="unknown", args={})),
            _tool_calling(),
        ),
        (
            types.Part(
                function_call=types.FunctionCall(name="search", args={"query": 3})
            ),
            _tool_calling(),
        ),
        (
            types.Part(
                function_call=types.FunctionCall(name="search", args={"query": "ok"})
            ),
            _tool_calling(ModelToolChoice.NONE),
        ),
    )
    provider = GoogleGenerateContentProvider()
    for part, tool_calling in cases:
        response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=[part]),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        )
        with (
            patch(
                "spakky.plugins.llm.providers.google.genai.Client",
                return_value=_RecordingClient(_RecordingModels(response)),
            ),
            pytest.raises(LlmResponseError),
        ):
            await provider.complete(
                _target(),
                _request(tool_calling=tool_calling),
            )


async def test_complete_rejects_empty_tool_catalog() -> None:
    """A tool-calling request must declare at least one native function."""
    request = _request(
        tool_calling=ToolCallingSpec(tools=(), choice=ModelToolChoice.AUTO)
    )

    with pytest.raises(LlmResponseError):
        await GoogleGenerateContentProvider().complete(_target(), request)


@pytest.mark.parametrize(
    ("choice", "expected_mode"),
    [
        (ModelToolChoice.AUTO, types.FunctionCallingConfigMode.AUTO),
        (ModelToolChoice.NONE, types.FunctionCallingConfigMode.NONE),
        (ModelToolChoice.REQUIRED, types.FunctionCallingConfigMode.ANY),
    ],
)
async def test_complete_maps_every_tool_choice_mode(
    choice: ModelToolChoice,
    expected_mode: types.FunctionCallingConfigMode,
) -> None:
    """Portable AUTO, NONE, and REQUIRED modes map to Gemini native modes."""
    response = None
    if choice is ModelToolChoice.REQUIRED:
        response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="search",
                                    args={"query": "required"},
                                )
                            )
                        ]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        )
    models = _RecordingModels(response)

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(models),
    ):
        await GoogleGenerateContentProvider().complete(
            _target(),
            _request(tool_calling=_tool_calling(choice)),
        )

    assert isinstance(models.config, types.GenerateContentConfig)
    assert models.config.tool_config is not None
    assert models.config.tool_config.function_calling_config is not None
    assert models.config.tool_config.function_calling_config.mode is expected_mode


async def test_complete_rejects_provider_tool_without_request_constraints() -> None:
    """A native call cannot exceed the caller-declared portable catalog."""
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="native-1",
                                name="native_tool",
                                args={"value": True},
                            )
                        )
                    ]
                ),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(response)),
        ),
        pytest.raises(LlmResponseError),
    ):
        await GoogleGenerateContentProvider().complete(_target(), _request())


async def test_stream_rejects_provider_tool_without_request_constraints() -> None:
    """Streaming cannot publish a tool candidate without caller authority."""
    chunks = (
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="native_tool",
                                    args={"value": True},
                                )
                            )
                        ]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
    )

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(chunks=chunks)),
        ),
        pytest.raises(LlmResponseError),
    ):
        await _collect(GoogleGenerateContentProvider(), _target(), _request())


@pytest.mark.parametrize("operation", ["complete", "stream"])
async def test_required_tool_choice_rejects_zero_calls(operation: str) -> None:
    """Complete and stream cannot silently weaken REQUIRED to AUTO."""
    response = _text_response("no tool")
    models = _RecordingModels(response=response, chunks=(response,))
    request = _request(tool_calling=_tool_calling(ModelToolChoice.REQUIRED))

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ),
        pytest.raises(LlmResponseError),
    ):
        if operation == "complete":
            await GoogleGenerateContentProvider().complete(_target(), request)
        else:
            await _collect(GoogleGenerateContentProvider(), _target(), request)


async def test_stream_maps_reasoning_text_tool_structured_usage_and_signature() -> None:
    """Streaming parts retain channel semantics, tool candidates, usage, and signatures."""
    reasoning_signature = b"reasoning-signature"
    tool_signature = b"tool-signature"
    chunks = (
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text="thinking",
                                thought=True,
                                thought_signature=reasoning_signature,
                            )
                        ],
                    )
                )
            ]
        ),
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(text='{"answer":"streamed"}'),
                            types.Part(
                                function_call=types.FunctionCall(
                                    id="call-stream",
                                    name="search",
                                    args={"query": "docs", "tags": []},
                                ),
                                thought_signature=tool_signature,
                            ),
                        ],
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=5,
                candidates_token_count=4,
                total_token_count=10,
            ),
        ),
    )
    models = _RecordingModels(chunks=chunks)
    client = _RecordingClient(models)
    request = _request(
        tool_calling=_tool_calling(),
        structured_output=_structured_output(),
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=client,
    ) as client_factory:
        events = await _collect(
            GoogleGenerateContentProvider(),
            _target(include_thoughts=True),
            request,
        )

    assert [event.kind for event in events] == [
        ModelStreamEventKind.REASONING_DELTA,
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        ModelStreamEventKind.STRUCTURED_OUTPUT,
        ModelStreamEventKind.DONE,
    ]
    reasoning, token, tool, structured, done = events
    assert reasoning.reasoning_delta == "thinking"
    assert reasoning.metadata["thought_signature"] == b64encode(
        reasoning_signature
    ).decode("ascii")
    assert token.token_delta == '{"answer":"streamed"}'
    assert tool.tool_call is not None
    assert tool.tool_call.call_id == "call-stream"
    assert tool.tool_call.arguments == {"query": "docs", "tags": ()}
    assert tool.tool_call.metadata["thought_signature"] == b64encode(
        tool_signature
    ).decode("ascii")
    assert structured.structured_output == {"answer": "streamed"}
    assert done.usage is not None
    assert done.usage.input_tokens == 5
    assert done.usage.output_tokens == 4
    assert done.usage.total_tokens == 10
    assert done.metadata == {
        "model_ref": "support/primary",
        "provider": "google",
        "profile": "google-developer",
        "model": "gemini-2.5-pro",
        "finish_reason": "STOP",
    }
    assert client.aio.entered is True
    assert client.aio.closed is True
    client_kwargs = client_factory.call_args.kwargs
    http_options = client_kwargs["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.timeout == 45_000
    assert isinstance(models.config, types.GenerateContentConfig)
    assert models.config.thinking_config is not None
    assert models.config.thinking_config.include_thoughts is True


async def test_stream_suppresses_unsolicited_reasoning_without_opt_in() -> None:
    """A provider cannot expose thought parts unless the profile requested them."""
    chunks = (
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(text="private", thought=True),
                            types.Part.from_text(text="visible"),
                        ]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(_RecordingModels(chunks=chunks)),
    ):
        events = await _collect(
            GoogleGenerateContentProvider(),
            _target(include_thoughts=False),
            _request(),
        )

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].token_delta == "visible"


async def test_stream_validates_structured_output_before_tool_candidate() -> None:
    """Invalid structured output cannot authorize an otherwise valid tool call."""
    chunks = (
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part.from_text(text='{"answer":3}'),
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="search",
                                    args={"query": "docs", "tags": []},
                                )
                            ),
                        ]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
    )
    observed: list[ModelStreamEvent] = []

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(chunks=chunks)),
        ),
        pytest.raises(LlmResponseError),
    ):
        async for event in GoogleGenerateContentProvider().stream(
            _target(),
            _request(
                tool_calling=_tool_calling(),
                structured_output=_structured_output(),
            ),
        ):
            observed.append(event)

    assert all(
        event.kind is not ModelStreamEventKind.TOOL_CALL_CANDIDATE for event in observed
    )


async def test_stream_skips_usage_only_chunks_and_honors_usage_opt_out() -> None:
    """Usage-only chunks do not emit text and usage opt-out leaves DONE empty."""
    chunks = (
        types.GenerateContentResponse(
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                total_token_count=3
            )
        ),
        _text_response("done"),
    )
    models = _RecordingModels(chunks=chunks)

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(models),
    ):
        events = await _collect(
            GoogleGenerateContentProvider(),
            _target(max_retries=0),
            _request(include_usage=False),
        )

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.DONE,
    ]
    assert events[-1].usage is None
    assert events[-1].metadata["finish_reason"] == "STOP"


async def test_stream_accepts_empty_candidate_content_and_empty_text_parts() -> None:
    """Non-payload stream chunks are ignored until the terminal DONE event."""
    chunks = (
        types.GenerateContentResponse(candidates=[types.Candidate(content=None)]),
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part.from_text(text="")]),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        ),
    )

    with patch(
        "spakky.plugins.llm.providers.google.genai.Client",
        return_value=_RecordingClient(_RecordingModels(chunks=chunks)),
    ):
        events = await _collect(
            GoogleGenerateContentProvider(),
            _target(),
            _request(),
        )

    assert len(events) == 1
    assert events[0].kind is ModelStreamEventKind.DONE


async def test_stream_rejects_eof_without_terminal_finish_reason() -> None:
    """An error-free early EOF cannot publish a partial assistant response as DONE."""
    chunks = (_text_response("partial", finish_reason=None),)

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(chunks=chunks)),
        ),
        pytest.raises(LlmResponseError),
    ):
        await _collect(GoogleGenerateContentProvider(), _target(), _request())


async def test_stream_withholds_tool_candidate_until_terminal_validation() -> None:
    """A tool cannot be dispatched before the provider terminal is validated."""
    chunks = (
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="search",
                                    args={"query": "partial"},
                                )
                            )
                        ]
                    )
                )
            ]
        ),
    )
    client = _RecordingClient(_RecordingModels(chunks=chunks))
    observed: list[ModelStreamEvent] = []

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=client,
        ),
        pytest.raises(LlmResponseError),
    ):
        async for event in GoogleGenerateContentProvider().stream(
            _target(),
            _request(tool_calling=_tool_calling()),
        ):
            observed.append(event)

    assert observed == []


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            types.GenerateContentResponse(
                prompt_feedback=types.GenerateContentResponsePromptFeedback(
                    block_reason=types.BlockedReason.BLOCKLIST
                )
            ),
            LlmModelRefusalError,
        ),
        (
            _text_response(
                "unsafe",
                finish_reason=types.FinishReason.PROHIBITED_CONTENT,
            ),
            LlmModelRefusalError,
        ),
        (
            _text_response("language", finish_reason=types.FinishReason.LANGUAGE),
            LlmModelRefusalError,
        ),
        (
            _text_response("no image", finish_reason=types.FinishReason.NO_IMAGE),
            LlmModelRefusalError,
        ),
        (
            _text_response(
                "invalid",
                finish_reason=types.FinishReason.UNEXPECTED_TOOL_CALL,
            ),
            LlmResponseError,
        ),
        (
            _text_response(
                "unspecified",
                finish_reason=types.FinishReason.FINISH_REASON_UNSPECIFIED,
            ),
            LlmResponseError,
        ),
        (
            _text_response("other", finish_reason=types.FinishReason.OTHER),
            LlmResponseError,
        ),
        (
            _text_response(
                "image other",
                finish_reason=types.FinishReason.IMAGE_OTHER,
            ),
            LlmResponseError,
        ),
    ],
)
async def test_stream_rejects_refusal_and_invalid_finish_reasons(
    response: types.GenerateContentResponse,
    expected: type[AbstractLlmError],
) -> None:
    """Streaming preserves typed refusal and invalid-response failures."""
    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(_RecordingModels(chunks=(response,))),
        ),
        pytest.raises(expected),
    ):
        await _collect(GoogleGenerateContentProvider(), _target(), _request())


async def test_stream_rejects_invalid_structured_output() -> None:
    """A completed streamed JSON document is validated before publication."""
    models = _RecordingModels(chunks=(_text_response('{"answer":3}'),))

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=_RecordingClient(models),
        ),
        pytest.raises(LlmResponseError),
    ):
        await _collect(
            GoogleGenerateContentProvider(),
            _target(),
            _request(structured_output=_structured_output()),
        )


@pytest.mark.parametrize(
    ("models", "expected_error"),
    [
        (
            _RecordingModels(
                stream_start_error=errors.ClientError(
                    504, {"message": "gateway timeout"}
                )
            ),
            LlmTimeoutError,
        ),
        (
            _RecordingModels(stream_error=httpx.ConnectError("offline")),
            LlmTransportError,
        ),
        (
            _RecordingModels(stream_error=httpx.ReadTimeout("slow")),
            LlmTimeoutError,
        ),
    ],
)
async def test_stream_normalizes_sdk_and_transport_failures(
    models: _RecordingModels,
    expected_error: type[AbstractLlmError],
) -> None:
    """Stream setup and iteration failures use the same stable error taxonomy."""
    client = _RecordingClient(models)

    with (
        patch(
            "spakky.plugins.llm.providers.google.genai.Client",
            return_value=client,
        ),
        pytest.raises(expected_error),
    ):
        await _collect(GoogleGenerateContentProvider(), _target(), _request())

    assert client.aio.entered is True
    assert client.aio.closed is True
