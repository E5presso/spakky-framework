"""CI-safe acceptance coverage for the spakky-llm plugin boundary."""

from collections.abc import AsyncIterator
from types import TracebackType
from typing import override
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import Message as AnthropicMessage
from google.auth.credentials import AnonymousCredentials
from google.genai import types as google_types
from openai.types.chat import ChatCompletion
import pytest
from pydantic import SecretStr
from spakky.agent import (
    IAgentModel,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import LlmConfigurationError
from spakky.plugins.llm.main import initialize
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    routing_metadata,
)
from spakky.plugins.llm.providers import anthropic as anthropic_provider
from spakky.plugins.llm.providers import google as google_provider
from spakky.plugins.llm.providers import openai as openai_provider
from spakky.plugins.llm.providers.anthropic import AnthropicMessagesProvider
from spakky.plugins.llm.providers.google import GoogleGenerateContentProvider
from spakky.plugins.llm.providers.openai import OpenAIChatProvider


class _FakeCompletions:
    """Record the SDK call while returning a typed official response model."""

    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def create(self, **request: object) -> ChatCompletion:
        self.request = request
        return ChatCompletion.model_validate(
            {
                "id": "chatcmpl-acceptance",
                "object": "chat.completion",
                "created": 1,
                "model": "served-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "official SDK boundary",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        )


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeAsyncOpenAI:
    """Minimal async lifecycle used by the official SDK adapter."""

    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)

    async def __aenter__(self) -> "_FakeAsyncOpenAI":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _FakeAnthropic:
    """Minimal Anthropic SDK context manager returning a typed Message."""

    def __init__(self) -> None:
        self.messages = MagicMock()
        self.messages.create = AsyncMock(
            return_value=AnthropicMessage.model_validate(
                {
                    "id": "msg-acceptance",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-opus-4-1",
                    "content": [{"type": "text", "text": "anthropic acceptance"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                }
            )
        )

    async def __aenter__(self) -> "_FakeAnthropic":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _FakeGoogleModels:
    """Record a Vertex GenerateContent request and return a typed response."""

    def __init__(self) -> None:
        self.model: str | None = None

    async def generate_content(
        self,
        *,
        model: str,
        contents: google_types.ContentListUnion | google_types.ContentListUnionDict,
        config: google_types.GenerateContentConfigOrDict | None = None,
    ) -> google_types.GenerateContentResponse:
        self.model = model
        return google_types.GenerateContentResponse(
            candidates=[
                google_types.Candidate(
                    content=google_types.Content(
                        role="model",
                        parts=[google_types.Part.from_text(text="vertex acceptance")],
                    ),
                    finish_reason=google_types.FinishReason.STOP,
                )
            ],
            usage_metadata=google_types.GenerateContentResponseUsageMetadata(
                prompt_token_count=3,
                candidates_token_count=2,
                total_token_count=5,
            ),
        )


class _FakeGoogleAsyncClient:
    def __init__(self, models: _FakeGoogleModels) -> None:
        self.models = models

    async def __aenter__(self) -> "_FakeGoogleAsyncClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _FakeGoogleClient:
    def __init__(self, models: _FakeGoogleModels) -> None:
        self.aio = _FakeGoogleAsyncClient(models)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _AcceptanceProvider(ILLMProvider):
    """No-network provider that records exact catalog targets."""

    def __init__(self, apis: frozenset[LlmProviderApi]) -> None:
        self.__apis = apis
        self.targets: list[LlmModelTarget] = []

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        return self.__apis

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        self.targets.append(target)
        content = request.messages[0].content
        assert isinstance(content, str)
        return ModelResponse(
            content=content,
            metadata=routing_metadata(target),
        )

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        return self._stream(target)

    async def _stream(
        self,
        target: LlmModelTarget,
    ) -> AsyncIterator[ModelStreamEvent]:
        yield done_event(target, "stop", None)


@Pod()
class _CustomOpenAIProvider(_AcceptanceProvider):
    """Application-contributed OpenAI-compatible replacement provider."""

    def __init__(self) -> None:
        super().__init__(frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}))


@Pod()
class _SecondCustomOpenAIProvider(_AcceptanceProvider):
    """Second user implementation used to prove startup ambiguity failure."""

    def __init__(self) -> None:
        super().__init__(frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}))


async def test_plugin_acceptance_routes_default_vllm_through_openai_sdk() -> None:
    """Plugin bootstrap부터 router와 공식 SDK mapping까지 한 경로로 동작한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.start()
    completions = _FakeCompletions()
    sdk = _FakeAsyncOpenAI(completions)
    constructor = MagicMock(return_value=sdk)

    with patch.object(openai_provider, "AsyncOpenAI", constructor):
        response = await app.container.get(IAgentModel).complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
            )
        )

    assert response.content == "official SDK boundary"
    assert response.usage.total_tokens == 5
    expected_metadata = {
        "model_ref": "assistant/default",
        "profile": "vllm-local",
        "provider": "vllm",
        "model": "default",
        "finish_reason": "stop",
        "response_id": "chatcmpl-acceptance",
        "response_model": "served-model",
    }
    assert all(
        response.metadata[key] == value for key, value in expected_metadata.items()
    )
    assert response.metadata["attempt_ordinal"] == 1
    assert completions.request is not None
    assert completions.request["model"] == "default"
    constructor.assert_called_once_with(
        api_key="EMPTY",
        admin_api_key="",
        base_url="http://127.0.0.1:8000/v1",
        organization="",
        project="",
        webhook_secret="",
        timeout=30.0,
        max_retries=0,
        default_headers={},
    )


async def test_plugin_initialize_custom_provider_replaces_first_party_default() -> None:
    """Normal plugin startup selects one user provider over a first-party default."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(_CustomOpenAIProvider)

    app.start()
    response = await app.container.get(IAgentModel).complete(
        ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "replace"),))
    )
    replacement = app.container.get(_CustomOpenAIProvider)

    assert response.content == "replace"
    assert len(replacement.targets) == 1
    assert replacement.targets[0].model_ref == "assistant/default"


def test_plugin_initialize_rejects_multiple_custom_provider_replacements() -> None:
    """Normal startup fails instead of choosing among multiple user providers."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(_CustomOpenAIProvider)
    app.add(_SecondCustomOpenAIProvider)

    with pytest.raises(LlmConfigurationError):
        app.start()


async def test_catalog_acceptance_routes_vertex_openrouter_vllm_and_anthropic() -> None:
    """Caller product refs resolve to four operator-internal backends without network."""
    config = LlmConfig(
        default_model="support/primary",
        profiles={
            "google-vertex": LlmProfile(
                provider="google",
                api=LlmProviderApi.GOOGLE_VERTEX,
                google_credential_strategy=GoogleCredentialStrategy.ADC,
                google_project="configured-project",
                google_location="us-central1",
            ),
            "openrouter": LlmProfile(
                provider="openrouter",
                api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                base_url="https://openrouter.example/v1",
                api_key=SecretStr("operator-secret"),
            ),
            "vllm-local": LlmProfile(
                provider="vllm",
                api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                base_url="http://localhost:8000/v1",
                openai_dialect=OpenAICompatibleDialect.VLLM,
            ),
            "anthropic": LlmProfile(
                provider="anthropic",
                api=LlmProviderApi.ANTHROPIC_MESSAGES,
                api_key=SecretStr("operator-secret"),
            ),
        },
        models={
            "support/primary": LlmModelRoute(
                profile="google-vertex",
                model="publishers/google/models/gemini-2.5-pro",
                capability=ModelCapability(
                    supports_tools=True,
                    supports_structured_output=True,
                ),
            ),
            "coding/primary": LlmModelRoute(
                profile="openrouter",
                model="moonshotai/kimi-k2",
            ),
            "local/primary": LlmModelRoute(
                profile="vllm-local",
                model="Qwen/Qwen3-8B",
                chat_template_kwargs={"enable_thinking": False},
            ),
            "analysis/primary": LlmModelRoute(
                profile="anthropic",
                model="claude-opus-4-1",
                capability=ModelCapability(supports_reasoning=True),
            ),
        },
    )
    google = _AcceptanceProvider(
        frozenset(
            {
                LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
                LlmProviderApi.GOOGLE_VERTEX,
            }
        )
    )
    openai = _AcceptanceProvider(frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}))
    anthropic = _AcceptanceProvider(frozenset({LlmProviderApi.ANTHROPIC_MESSAGES}))
    model = LlmAgentModel(config, (google, openai, anthropic))
    expected = (
        (
            "support/primary",
            "google-vertex",
            "google",
            "publishers/google/models/gemini-2.5-pro",
        ),
        ("coding/primary", "openrouter", "openrouter", "moonshotai/kimi-k2"),
        ("local/primary", "vllm-local", "vllm", "Qwen/Qwen3-8B"),
        ("analysis/primary", "anthropic", "anthropic", "claude-opus-4-1"),
    )

    for model_ref, profile, provider, physical_model in expected:
        response = await model.complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "acceptance"),),
                model_selection=ModelSelection(model_ref=model_ref),
            )
        )
        expected_metadata = {
            "model_ref": model_ref,
            "profile": profile,
            "provider": provider,
            "model": physical_model,
        }
        assert all(
            response.metadata[key] == value for key, value in expected_metadata.items()
        )
        assert response.metadata["attempt_ordinal"] == 1

    assert google.targets[0].model_ref == "support/primary"
    assert openai.targets[0].model == "moonshotai/kimi-k2"
    assert openai.targets[1].model == "Qwen/Qwen3-8B"
    assert anthropic.targets[0].model_ref == "analysis/primary"


async def test_openrouter_logical_route_crosses_standard_openai_sdk_boundary() -> None:
    """OpenRouter remains a standard OpenAI-compatible connection behind a logical ref."""
    completions = _FakeCompletions()
    constructor = MagicMock(return_value=_FakeAsyncOpenAI(completions))
    config = LlmConfig(
        default_model="coding/primary",
        profiles={
            "openrouter": LlmProfile(
                provider="openrouter",
                api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                base_url="https://openrouter.example/v1",
                api_key=SecretStr("operator-secret"),
            )
        },
        models={
            "coding/primary": LlmModelRoute(
                profile="openrouter",
                model="moonshotai/kimi-k2",
            )
        },
    )
    model = LlmAgentModel(config, (OpenAIChatProvider(),))

    with patch.object(openai_provider, "AsyncOpenAI", constructor):
        response = await model.complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
                model_selection=ModelSelection(model_ref="coding/primary"),
            )
        )

    assert completions.request is not None
    assert completions.request["model"] == "moonshotai/kimi-k2"
    assert response.metadata["model_ref"] == "coding/primary"
    assert response.metadata["profile"] == "openrouter"
    assert response.metadata["provider"] == "openrouter"
    assert response.metadata["model"] == "moonshotai/kimi-k2"
    assert constructor.call_args.kwargs["base_url"] == "https://openrouter.example/v1"


async def test_anthropic_logical_route_crosses_native_messages_sdk_boundary() -> None:
    """Anthropic logical route reaches the native Messages adapter with exact evidence."""
    sdk = _FakeAnthropic()
    constructor = MagicMock(return_value=sdk)
    config = LlmConfig(
        default_model="analysis/primary",
        profiles={
            "anthropic": LlmProfile(
                provider="anthropic",
                api=LlmProviderApi.ANTHROPIC_MESSAGES,
                api_key=SecretStr("operator-secret"),
            )
        },
        models={
            "analysis/primary": LlmModelRoute(
                profile="anthropic",
                model="claude-opus-4-1",
            )
        },
    )
    model = LlmAgentModel(config, (AnthropicMessagesProvider(),))

    with patch.object(anthropic_provider, "AsyncAnthropic", constructor):
        response = await model.complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
                model_selection=ModelSelection(model_ref="analysis/primary"),
            )
        )

    assert sdk.messages.create.await_args.kwargs["model"] == "claude-opus-4-1"
    assert response.content == "anthropic acceptance"
    expected_metadata = {
        "model_ref": "analysis/primary",
        "profile": "anthropic",
        "provider": "anthropic",
        "model": "claude-opus-4-1",
        "finish_reason": "end_turn",
    }
    assert all(
        response.metadata[key] == value for key, value in expected_metadata.items()
    )
    assert response.metadata["attempt_ordinal"] == 1


async def test_vertex_logical_route_crosses_explicit_adc_sdk_boundary() -> None:
    """Vertex route selects ADC explicitly and passes configured project/location."""
    credentials = AnonymousCredentials()
    models = _FakeGoogleModels()
    sdk = _FakeGoogleClient(models)
    constructor = MagicMock(return_value=sdk)
    config = LlmConfig(
        default_model="support/primary",
        profiles={
            "google-vertex": LlmProfile(
                provider="google",
                api=LlmProviderApi.GOOGLE_VERTEX,
                google_credential_strategy=GoogleCredentialStrategy.ADC,
                google_project="configured-project",
                google_location="us-central1",
            )
        },
        models={
            "support/primary": LlmModelRoute(
                profile="google-vertex",
                model="publishers/google/models/gemini-2.5-pro",
            )
        },
    )
    model = LlmAgentModel(config, (GoogleGenerateContentProvider(),))

    with (
        patch.object(
            google_provider.google.auth,
            "default",
            return_value=(credentials, "ambient-project"),
        ),
        patch.object(google_provider.genai, "Client", constructor),
    ):
        response = await model.complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
                model_selection=ModelSelection(model_ref="support/primary"),
            )
        )

    assert models.model == "publishers/google/models/gemini-2.5-pro"
    assert sdk.closed is True
    kwargs = constructor.call_args.kwargs
    assert kwargs["enterprise"] is True
    assert kwargs["credentials"] is credentials
    assert kwargs["project"] == "configured-project"
    assert kwargs["location"] == "us-central1"
    http_options = kwargs["http_options"]
    assert isinstance(http_options, google_types.HttpOptions)
    assert http_options.base_url == "https://us-central1-aiplatform.googleapis.com/"
    expected_metadata = {
        "model_ref": "support/primary",
        "profile": "google-vertex",
        "provider": "google",
        "model": "publishers/google/models/gemini-2.5-pro",
        "finish_reason": "STOP",
    }
    assert all(
        response.metadata[key] == value for key, value in expected_metadata.items()
    )
    assert response.metadata["attempt_ordinal"] == 1
