"""Provider adapter contract and resolved model target."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from spakky.agent import (
    JsonObject,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelUsage,
)

from spakky.plugins.llm.config import LlmModelRoute, LlmProfile, LlmProviderApi
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
    """One opaque model ref resolved against the operator-owned catalog."""

    model_ref: str
    profile_name: str
    profile: LlmProfile
    route: LlmModelRoute

    @property
    def model(self) -> str:
        """Return the physical provider model from the resolved route."""
        return self.route.model


class ILLMProvider(ABC):
    """Native SDK adapter for one provider API family."""

    @property
    @abstractmethod
    def apis(self) -> frozenset[LlmProviderApi]:
        """Return every API family implemented by this adapter."""
        ...

    @property
    def is_default(self) -> bool:
        """Return whether this is a replaceable first-party default adapter."""
        return False

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


def routing_metadata(target: LlmModelTarget) -> JsonObject:
    """Return privacy-safe evidence for the exact resolved catalog route."""
    return {
        "model_ref": target.model_ref,
        "profile": target.profile_name,
        "provider": target.profile.provider,
        "model": target.model,
    }


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
        metadata=routing_metadata(target),
    )


def error_event(
    error: AbstractLlmError,
    target: LlmModelTarget,
) -> ModelStreamEvent:
    """Return one normalized terminal error event."""
    return ModelStreamEvent(
        kind=ModelStreamEventKind.ERROR,
        error=to_model_error(error, target),
        metadata=routing_metadata(target),
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
        metadata={**routing_metadata(target), "finish_reason": finish_reason},
    )
