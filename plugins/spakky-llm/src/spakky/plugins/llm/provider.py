"""Provider adapter contract and resolved model target."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from spakky.agent import (
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelUsage,
)

from spakky.plugins.llm.config import LlmProfile, LlmProviderApi
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


@dataclass(frozen=True, slots=True)
class LlmModelTarget:
    """One request resolved against an operator-owned profile."""

    profile_name: str
    profile: LlmProfile
    model: str


class ILLMProvider(ABC):
    """Native SDK adapter for one provider API family."""

    @property
    @abstractmethod
    def api(self) -> LlmProviderApi:
        """Return the API family implemented by this adapter."""
        ...

    @abstractmethod
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        """Return one provider-neutral completion."""
        ...

    @abstractmethod
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Return provider-neutral streaming events."""
        ...


def ensure_tool_call_allowed(request: ModelRequest) -> None:
    """Reject a provider tool call that lacks caller-declared authority."""
    tool_calling = request.tool_calling
    if tool_calling is None or tool_calling.choice is ModelToolChoice.NONE:
        raise LlmResponseError


def ensure_terminal_tool_choice(
    request: ModelRequest,
    tool_call_count: int,
) -> None:
    """Validate the terminal tool-call count against the requested choice."""
    tool_calling = request.tool_calling
    if tool_call_count > 0:
        ensure_tool_call_allowed(request)
    if (
        tool_calling is not None
        and tool_calling.choice is ModelToolChoice.REQUIRED
        and tool_call_count == 0
    ):
        raise LlmResponseError


def to_model_error(error: AbstractLlmError, target: LlmModelTarget) -> ModelError:
    """Normalize one adapter exception for the public streaming error channel."""
    code = "llm_response_error"
    retryable = False
    if isinstance(error, LlmTimeoutError):
        code = "llm_timeout"
        retryable = True
    elif isinstance(error, LlmTransportError):
        code = "llm_transport_error"
        retryable = True
    elif isinstance(error, LlmStreamingDisabledError):
        code = "llm_streaming_disabled"
    elif isinstance(error, LlmConfigurationError):
        code = "llm_configuration_invalid"
    elif isinstance(error, LlmModelSelectionError):
        code = "llm_model_selection_invalid"
    elif isinstance(error, LlmProviderUnavailableError):
        code = "llm_provider_unavailable"
    elif isinstance(error, LlmUnsupportedFeatureError):
        code = "llm_feature_unsupported"
    elif isinstance(error, LlmModelRefusalError):
        code = "model_refusal"
    elif isinstance(error, LlmResponseError):
        code = "llm_response_error"
    return ModelError(
        code=code,
        message=error.message,
        retryable=retryable,
        metadata={
            "provider": target.profile.provider,
            "profile": target.profile_name,
        },
    )


def error_event(
    error: AbstractLlmError,
    target: LlmModelTarget,
) -> ModelStreamEvent:
    """Return one normalized terminal error event."""
    return ModelStreamEvent(
        kind=ModelStreamEventKind.ERROR,
        error=to_model_error(error, target),
    )


def done_event(
    target: LlmModelTarget,
    finish_reason: str | None,
    usage: ModelUsage | None,
) -> ModelStreamEvent:
    """Return one provider-neutral terminal stream event."""
    return ModelStreamEvent(
        kind=ModelStreamEventKind.DONE,
        usage=usage,
        metadata={
            "provider": target.profile.provider,
            "profile": target.profile_name,
            "finish_reason": finish_reason,
        },
    )
