"""Tests for operator-catalog LLM routing."""

from collections.abc import AsyncIterator
from typing import override

import pytest
from pydantic import SecretStr
from spakky.agent import (
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelModality,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
)

from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmModelSelectionError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmStreamingDisabledError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    error_event,
    to_model_error,
)


class RecordingProvider(ILLMProvider):
    """Deterministic collection-injected provider used to verify routing."""

    def __init__(
        self,
        apis: frozenset[LlmProviderApi],
        *,
        response: ModelResponse | None = None,
        events: tuple[ModelStreamEvent, ...] = (),
        stream_error: AbstractLlmError | None = None,
        is_default: bool = False,
    ) -> None:
        self.__apis = apis
        self.__is_default = is_default
        self.response = response or ModelResponse(content="ok")
        self.events = events
        self.stream_error = stream_error
        self.target: LlmModelTarget | None = None
        self.request: ModelRequest | None = None

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        return self.__apis

    @property
    @override
    def is_default(self) -> bool:
        return self.__is_default

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        self.target = target
        self.request = request
        return self.response

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.target = target
        self.request = request
        return self._stream()

    async def _stream(self) -> AsyncIterator[ModelStreamEvent]:
        if self.stream_error is not None:
            raise self.stream_error
        for event in self.events:
            yield event


class UnknownLlmError(AbstractLlmError):
    """Exercise the stable fallback for future provider-specific errors."""

    message = "Unknown provider failure"


def _request(selection: ModelSelection | None = None) -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        model_selection=selection,
    )


def _vllm_profile(*, stream_enabled: bool = True) -> LlmProfile:
    return LlmProfile(
        provider="vllm",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        base_url="http://localhost:8000/v1",
        api_key=SecretStr("EMPTY"),
        stream_enabled=stream_enabled,
        openai_dialect=OpenAICompatibleDialect.VLLM,
    )


def _anthropic_profile() -> LlmProfile:
    return LlmProfile(
        provider="anthropic",
        api=LlmProviderApi.ANTHROPIC_MESSAGES,
        api_key=SecretStr("secret"),
    )


def _full_capability() -> ModelCapability:
    return ModelCapability(
        supports_reasoning=True,
        context_window_tokens=200_000,
        supports_token_counting=True,
        input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
        output_modalities=frozenset({ModelModality.TEXT}),
        supports_tools=True,
        supports_structured_output=True,
    )


def _config(*, stream_enabled: bool = True) -> LlmConfig:
    return LlmConfig(
        default_model="assistant/default",
        profiles={
            "vllm-local": _vllm_profile(stream_enabled=stream_enabled),
            "anthropic": _anthropic_profile(),
        },
        models={
            "assistant/default": LlmModelRoute(
                profile="vllm-local",
                model="default",
                capability=ModelCapability(
                    supports_tools=True,
                    supports_structured_output=True,
                ),
            ),
            "support/primary": LlmModelRoute(
                profile="vllm-local",
                model="Qwen/Qwen3-8B",
                chat_template_kwargs={"enable_thinking": False},
            ),
            "analysis/primary": LlmModelRoute(
                profile="anthropic",
                model="claude-opus-4-1",
                capability=_full_capability(),
            ),
        },
    )


def _openai_provider(
    events: tuple[ModelStreamEvent, ...] = (),
) -> RecordingProvider:
    """Build the singleton OpenAI API test provider."""
    return RecordingProvider(
        frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}),
        events=events,
    )


def _anthropic_provider() -> RecordingProvider:
    """Build the singleton Anthropic API test provider."""
    return RecordingProvider(
        frozenset({LlmProviderApi.ANTHROPIC_MESSAGES}),
    )


async def test_complete_routes_default_and_exact_opaque_model_refs() -> None:
    """Default와 caller logical ref가 정확한 catalog route로 전달된다."""
    openai = _openai_provider()
    anthropic = _anthropic_provider()
    model = LlmAgentModel(_config(), (openai, anthropic))

    await model.complete(_request())
    assert openai.target is not None
    assert openai.target.model_ref == "assistant/default"
    assert openai.target.profile_name == "vllm-local"
    assert openai.target.model == "default"

    await model.complete(_request(ModelSelection(model_ref="analysis/primary")))
    assert anthropic.target is not None
    assert anthropic.target.model_ref == "analysis/primary"
    assert anthropic.target.profile_name == "anthropic"
    assert anthropic.target.model == "claude-opus-4-1"


async def test_complete_preserves_slashes_without_raw_model_fallback() -> None:
    """Logical ref와 physical model의 slash는 서로 해석하거나 분해하지 않는다."""
    provider = _openai_provider()
    model = LlmAgentModel(_config(), (provider, _anthropic_provider()))

    await model.complete(_request(ModelSelection(model_ref="support/primary")))

    assert provider.target is not None
    assert provider.target.model_ref == "support/primary"
    assert provider.target.model == "Qwen/Qwen3-8B"

    with pytest.raises(LlmModelSelectionError):
        await model.complete(_request(ModelSelection(model_ref="Qwen/Qwen3-8B")))


async def test_request_metadata_cannot_override_connection_or_provider_model() -> None:
    """Caller metadata의 credential/endpoint/model 값은 routing authority가 아니다."""
    provider = _openai_provider()
    model = LlmAgentModel(_config(), (provider, _anthropic_provider()))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        model_selection=ModelSelection(model_ref="support/primary"),
        metadata={
            "api_key": "caller-secret",
            "base_url": "https://attacker.invalid/v1",
            "model": "attacker/model",
        },
    )

    await model.complete(request)

    assert provider.target is not None
    assert provider.target.profile.api_key_value() == "EMPTY"
    assert provider.target.profile.base_url == "http://localhost:8000/v1"
    assert provider.target.model == "Qwen/Qwen3-8B"


async def test_complete_treats_opaque_refs_as_case_sensitive() -> None:
    """Opaque model ref는 trim 외의 case canonicalization을 받지 않는다."""
    model = LlmAgentModel(
        _config(),
        (_openai_provider(), _anthropic_provider()),
    )

    with pytest.raises(LlmModelSelectionError):
        await model.complete(_request(ModelSelection(model_ref="Support/Primary")))


def test_capability_is_preserved_per_route() -> None:
    """같은 router가 selected route의 full capability를 손실 없이 반환한다."""
    model = LlmAgentModel(
        _config(),
        (_openai_provider(), _anthropic_provider()),
    )

    assert model.capability == ModelCapability(
        supports_tools=True,
        supports_structured_output=True,
    )
    assert (
        model.capability_for(ModelSelection(model_ref="analysis/primary"))
        == _full_capability()
    )


async def test_router_uses_bootstrap_catalog_snapshot_after_config_mutation() -> None:
    """Bootstrap 뒤 외부 dict mutation은 effective routing을 바꾸지 못한다."""
    config = _config()
    provider = _openai_provider()
    model = LlmAgentModel(config, (provider, _anthropic_provider()))
    config.default_model = "analysis/primary"
    config.models["support/primary"] = LlmModelRoute(
        profile="anthropic",
        model="attacker/model",
    )
    config.profiles["vllm-local"] = _anthropic_profile()
    config.models["support/primary"].chat_template_kwargs["enable_thinking"] = True

    await model.complete(_request())
    assert provider.target is not None
    assert provider.target.model_ref == "assistant/default"
    assert provider.target.model == "default"

    await model.complete(_request(ModelSelection(model_ref="support/primary")))

    assert provider.target is not None
    assert provider.target.profile_name == "vllm-local"
    assert provider.target.profile.provider == "vllm"
    assert provider.target.model == "Qwen/Qwen3-8B"
    assert provider.target.route.chat_template_kwargs == {"enable_thinking": False}


@pytest.mark.parametrize("model_ref", ["missing", "provider/model/raw"])
async def test_complete_rejects_unknown_model_refs(model_ref: str) -> None:
    """Catalog 밖 ref는 profile/model 추론이나 raw override 없이 거부된다."""
    model = LlmAgentModel(
        _config(),
        (_openai_provider(), _anthropic_provider()),
    )

    with pytest.raises(LlmModelSelectionError):
        await model.complete(_request(ModelSelection(model_ref=model_ref)))


@pytest.mark.parametrize(
    "providers",
    [
        (),
        (RecordingProvider(frozenset()),),
        (_openai_provider(), _openai_provider()),
        (
            RecordingProvider(
                frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}),
                is_default=True,
            ),
            RecordingProvider(
                frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}),
                is_default=True,
            ),
            _anthropic_provider(),
        ),
        (
            RecordingProvider(
                frozenset(
                    {
                        LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
                        LlmProviderApi.GOOGLE_VERTEX,
                    }
                )
            ),
        ),
    ],
)
def test_model_rejects_missing_empty_overlap_or_unconfigured_provider_sets(
    providers: tuple[ILLMProvider, ...],
) -> None:
    """Collection registry는 configured API마다 유일하고 nonempty한 구현을 요구한다."""
    with pytest.raises(LlmConfigurationError):
        LlmAgentModel(_config(), providers)


async def test_user_provider_replaces_first_party_default_for_same_api() -> None:
    """Exactly one non-default implementation replaces same-API defaults."""
    first_party = RecordingProvider(
        frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}),
        is_default=True,
    )
    replacement = _openai_provider()
    model = LlmAgentModel(
        _config(),
        (first_party, replacement, _anthropic_provider()),
    )

    await model.complete(_request())

    assert first_party.target is None
    assert replacement.target is not None
    assert replacement.target.model_ref == "assistant/default"


def test_model_accepts_one_provider_implementing_both_google_apis() -> None:
    """한 Google provider는 plural registry를 통해 두 Google API를 구현할 수 있다."""
    google = RecordingProvider(
        frozenset(
            {
                LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
                LlmProviderApi.GOOGLE_VERTEX,
            }
        )
    )
    config = LlmConfig(
        default_model="support/primary",
        profiles={
            "google-developer": LlmProfile.model_construct(
                provider="google",
                api=LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
                api_key=SecretStr("secret"),
                google_credential_strategy=GoogleCredentialStrategy.API_KEY,
            ),
            "google-vertex": LlmProfile.model_construct(
                provider="google",
                api=LlmProviderApi.GOOGLE_VERTEX,
                google_credential_strategy=GoogleCredentialStrategy.ADC,
                google_project="project-a",
                google_location="us-central1",
            ),
        },
        models={
            "support/primary": LlmModelRoute(
                profile="google-vertex",
                model="gemini-2.5-pro",
            ),
            "support/fast": LlmModelRoute(
                profile="google-developer",
                model="gemini-2.5-flash",
            ),
        },
    )

    model = LlmAgentModel(config, (google,))

    assert model.capability == ModelCapability()


def test_router_defensive_fences_reject_invalid_constructed_state() -> None:
    """Bypassed config validation still cannot expose a missing profile/provider."""
    route = LlmModelRoute(profile="missing", model="model-id")
    invalid = LlmConfig.model_construct(
        default_model="support/primary",
        profiles={},
        models={"support/primary": route},
    )
    model = LlmAgentModel(invalid, (_openai_provider(),))

    with pytest.raises(LlmModelSelectionError):
        _ = model.capability

    foreign_target = LlmModelTarget(
        model_ref="analysis/primary",
        profile_name="anthropic",
        profile=_anthropic_profile(),
        route=LlmModelRoute(profile="anthropic", model="claude-opus-4-1"),
    )
    with pytest.raises(LlmProviderUnavailableError):
        model._provider_for(foreign_target)


async def test_stream_passes_events_and_normalizes_resolved_failure() -> None:
    """정상 event는 보존하고 resolved provider 예외는 routing evidence로 닫는다."""
    token = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="hi",
    )
    provider = _openai_provider(events=(token,))
    model = LlmAgentModel(_config(), (provider, _anthropic_provider()))

    success = [event async for event in model.stream(_request())]
    provider.stream_error = LlmTimeoutError()
    failure = [event async for event in model.stream(_request())]

    assert success == [token]
    assert [event.kind for event in failure] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert failure[0].error is not None
    assert failure[0].error.code == "llm_timeout"
    assert failure[0].error.retryable is True
    assert failure[0].metadata == {
        "model_ref": "assistant/default",
        "profile": "vllm-local",
        "provider": "vllm",
        "model": "default",
    }


async def test_stream_disabled_is_terminal_with_resolved_route_evidence() -> None:
    """Profile stream 정책 오류도 exact route metadata와 함께 terminalize 된다."""
    model = LlmAgentModel(
        _config(stream_enabled=False),
        (_openai_provider(), _anthropic_provider()),
    )

    events = [event async for event in model.stream(_request())]

    assert events[0].error is not None
    assert events[0].error.code == "llm_streaming_disabled"
    assert events[0].metadata["model_ref"] == "assistant/default"


async def test_stream_unknown_ref_does_not_fabricate_default_route_evidence() -> None:
    """Unresolved ref error는 선택되지 않은 default profile/model을 기록하지 않는다."""
    model = LlmAgentModel(
        _config(),
        (_openai_provider(), _anthropic_provider()),
    )

    events = [
        event
        async for event in model.stream(
            _request(ModelSelection(model_ref="missing/route"))
        )
    ]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].metadata == {"model_ref": "missing/route"}
    assert events[0].error is not None
    assert events[0].error.metadata == {"model_ref": "missing/route"}
    assert events[1].metadata == {"model_ref": "missing/route"}


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (LlmTimeoutError(), "llm_timeout", True),
        (LlmTransportError(), "llm_transport_error", True),
        (LlmStreamingDisabledError(), "llm_streaming_disabled", False),
        (LlmModelSelectionError(), "llm_model_selection_invalid", False),
        (LlmProviderUnavailableError(), "llm_provider_unavailable", False),
        (LlmUnsupportedFeatureError(), "llm_feature_unsupported", False),
        (LlmModelRefusalError(), "model_refusal", False),
        (LlmResponseError(), "llm_response_error", False),
        (LlmConfigurationError(), "llm_configuration_invalid", False),
        (UnknownLlmError(), "llm_response_error", False),
    ],
)
def test_provider_errors_have_stable_codes_and_routing_evidence(
    error: AbstractLlmError,
    code: str,
    retryable: bool,
) -> None:
    """Provider 예외 계층은 stable code와 canonical route evidence를 보존한다."""
    target = LlmModelTarget(
        model_ref="assistant/default",
        profile_name="vllm-local",
        profile=_vllm_profile(),
        route=LlmModelRoute(profile="vllm-local", model="default"),
    )

    normalized = to_model_error(error, target)

    assert normalized.code == code
    assert normalized.retryable is retryable
    assert normalized.metadata == {
        "model_ref": "assistant/default",
        "profile": "vllm-local",
        "provider": "vllm",
        "model": "default",
    }


def test_provider_event_helpers_preserve_terminal_metadata() -> None:
    """공통 helper는 canonical route, finish reason, usage를 보존한다."""
    target = LlmModelTarget(
        model_ref="assistant/default",
        profile_name="vllm-local",
        profile=_vllm_profile(),
        route=LlmModelRoute(profile="vllm-local", model="default"),
    )
    usage = ModelUsage(input_tokens=2, output_tokens=1, total_tokens=3)

    failed = error_event(LlmResponseError(), target)
    done = done_event(target, "stop", usage)

    assert failed.kind == ModelStreamEventKind.ERROR
    assert failed.metadata == {
        "model_ref": "assistant/default",
        "profile": "vllm-local",
        "provider": "vllm",
        "model": "default",
    }
    assert done.kind == ModelStreamEventKind.DONE
    assert done.usage == usage
    assert done.metadata == {
        "model_ref": "assistant/default",
        "profile": "vllm-local",
        "provider": "vllm",
        "model": "default",
        "finish_reason": "stop",
    }
