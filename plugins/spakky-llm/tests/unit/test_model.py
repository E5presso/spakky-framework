"""Tests for allowlisted LLM profile routing."""

from collections.abc import AsyncIterator
from typing import override

import pytest
from spakky.agent import (
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
)

from spakky.plugins.llm.config import LlmConfig, LlmProfile, LlmProviderApi
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
    """Deterministic provider used to verify router behavior."""

    def __init__(
        self,
        api: LlmProviderApi,
        *,
        response: ModelResponse | None = None,
        events: tuple[ModelStreamEvent, ...] = (),
        stream_error: AbstractLlmError | None = None,
    ) -> None:
        self.__api = api
        self.response = response or ModelResponse(content="ok")
        self.events = events
        self.stream_error = stream_error
        self.target: LlmModelTarget | None = None
        self.request: ModelRequest | None = None

    @property
    @override
    def api(self) -> LlmProviderApi:
        return self.__api

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
    """Exercise the stable fallback for future provider-specific error types."""

    message = "Unknown provider failure"


def _request(selection: ModelSelection | None = None) -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        model_selection=selection,
    )


def _config_with_profiles() -> LlmConfig:
    config = LlmConfig()
    config.profiles["claude"] = LlmProfile(
        provider="anthropic",
        api=LlmProviderApi.ANTHROPIC_MESSAGES,
        model="claude-opus-4-1",
        supports_reasoning=True,
        context_window_tokens=200_000,
        supports_token_counting=True,
    )
    return config


async def test_complete_routes_default_and_selected_native_profiles() -> None:
    """default와 요청별 profile이 각각 올바른 SDK adapter로 전달된다."""
    openai = RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS)
    anthropic = RecordingProvider(LlmProviderApi.ANTHROPIC_MESSAGES)
    model = LlmAgentModel(_config_with_profiles(), (openai, anthropic))

    default_response = await model.complete(_request())
    selected_response = await model.complete(
        _request(
            ModelSelection(
                provider="anthropic",
                profile="claude",
                model="claude-sonnet-4-5",
                metadata={"base_url": "https://attacker.invalid"},
            )
        )
    )

    assert default_response.content == "ok"
    assert selected_response.content == "ok"
    assert openai.target is not None
    assert openai.target.profile_name == "default"
    assert anthropic.target is not None
    assert anthropic.target.model == "claude-sonnet-4-5"
    assert anthropic.target.profile.base_url is None


async def test_complete_allows_model_only_override_on_default_profile() -> None:
    """Provider/profile이 생략된 selector는 default 연결의 model만 바꾼다."""
    openai = RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS)
    model = LlmAgentModel(LlmConfig(), (openai,))

    await model.complete(_request(ModelSelection(model="served-alias")))

    assert openai.target is not None
    assert openai.target.profile_name == "default"
    assert openai.target.model == "served-alias"


def test_capability_is_resolved_per_profile() -> None:
    """runner가 호출 전에 선택 profile의 capability를 조회할 수 있다."""
    model = LlmAgentModel(
        _config_with_profiles(),
        (
            RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            RecordingProvider(LlmProviderApi.ANTHROPIC_MESSAGES),
        ),
    )

    assert model.capability == ModelCapability()
    assert model.capability_for(
        ModelSelection(provider="anthropic")
    ) == ModelCapability(
        supports_reasoning=True,
        context_window_tokens=200_000,
        supports_token_counting=True,
    )


@pytest.mark.parametrize(
    "selection",
    [
        ModelSelection(profile="missing"),
        ModelSelection(profile="claude", provider="google"),
        ModelSelection(provider="missing"),
    ],
)
async def test_complete_rejects_unallowlisted_or_mismatched_selection(
    selection: ModelSelection,
) -> None:
    """외부 selector는 등록되지 않은 연결 설정을 만들 수 없다."""
    model = LlmAgentModel(
        _config_with_profiles(),
        (
            RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            RecordingProvider(LlmProviderApi.ANTHROPIC_MESSAGES),
        ),
    )

    with pytest.raises(LlmModelSelectionError):
        await model.complete(_request(selection))


async def test_complete_rejects_ambiguous_provider_without_profile() -> None:
    """같은 provider의 profile이 여러 개면 명시적인 profile 선택을 요구한다."""
    config = _config_with_profiles()
    config.profiles["claude-backup"] = config.profiles["claude"].model_copy()
    model = LlmAgentModel(
        config,
        (
            RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            RecordingProvider(LlmProviderApi.ANTHROPIC_MESSAGES),
        ),
    )

    with pytest.raises(LlmModelSelectionError):
        await model.complete(_request(ModelSelection(provider="anthropic")))


@pytest.mark.parametrize(
    "providers",
    [
        (),
        (
            RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
        ),
    ],
)
def test_model_rejects_missing_or_duplicate_provider_adapters(
    providers: tuple[ILLMProvider, ...],
) -> None:
    """API adapter registry는 구성된 API마다 정확히 하나의 구현을 요구한다."""
    with pytest.raises(LlmConfigurationError):
        LlmAgentModel(LlmConfig(), providers)


async def test_model_rejects_profile_added_without_registered_adapter() -> None:
    """런타임에 추가된 profile도 등록되지 않은 API adapter를 사용할 수 없다."""
    config = LlmConfig()
    model = LlmAgentModel(
        config,
        (RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),),
    )
    config.profiles["google"] = LlmProfile(
        provider="google",
        api=LlmProviderApi.GOOGLE_GENERATE_CONTENT,
        model="gemini",
    )

    with pytest.raises(LlmProviderUnavailableError):
        await model.complete(_request(ModelSelection(profile="google")))


async def test_stream_passes_provider_events_and_normalizes_failure() -> None:
    """정상 provider event는 보존하고 adapter 예외는 ERROR/DONE으로 닫는다."""
    token = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="hi",
    )
    provider = RecordingProvider(
        LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        events=(token,),
    )
    model = LlmAgentModel(LlmConfig(), (provider,))

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


async def test_stream_disabled_and_invalid_selection_are_terminal_events() -> None:
    """stream 설정과 selector 오류는 호출자에게 terminal event로 전달된다."""
    config = LlmConfig()
    config.profiles["default"].stream_enabled = False
    model = LlmAgentModel(
        config,
        (RecordingProvider(LlmProviderApi.OPENAI_CHAT_COMPLETIONS),),
    )

    disabled = [event async for event in model.stream(_request())]
    invalid = [
        event
        async for event in model.stream(_request(ModelSelection(profile="missing")))
    ]

    assert disabled[0].error is not None
    assert disabled[0].error.code == "llm_streaming_disabled"
    assert invalid[0].error is not None
    assert invalid[0].error.code == "llm_model_selection_invalid"


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
def test_provider_errors_have_stable_stream_codes(
    error: AbstractLlmError,
    code: str,
    retryable: bool,
) -> None:
    """provider 예외 계층은 안정적인 public ModelError code로 정규화된다."""
    target = LlmModelTarget(
        profile_name="default",
        profile=LlmConfig().profiles["default"],
        model="default",
    )

    normalized = to_model_error(error, target)

    assert normalized.code == code
    assert normalized.retryable is retryable
    assert normalized.metadata == {"provider": "vllm", "profile": "default"}


def test_provider_event_helpers_preserve_terminal_metadata() -> None:
    """공통 helper는 provider/profile/finish reason과 usage를 보존한다."""
    target = LlmModelTarget(
        profile_name="default",
        profile=LlmConfig().profiles["default"],
        model="default",
    )
    usage = ModelUsage(input_tokens=2, output_tokens=1, total_tokens=3)

    failed = error_event(LlmResponseError(), target)
    done = done_event(target, "stop", usage)

    assert failed.kind == ModelStreamEventKind.ERROR
    assert done.kind == ModelStreamEventKind.DONE
    assert done.usage == usage
    assert done.metadata == {
        "provider": "vllm",
        "profile": "default",
        "finish_reason": "stop",
    }
