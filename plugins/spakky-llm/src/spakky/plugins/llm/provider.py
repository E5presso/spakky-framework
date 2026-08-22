"""Provider adapter contract and resolved model target."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum

from spakky.agent import (
    JsonObject,
    JsonValue,
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
    LlmCapabilityError,
    LlmCacheConfigurationError,
    LlmCircuitOpenError,
    LlmConcurrencyLimitError,
    LlmFailureClass,
    LlmModelRefusalError,
    LlmModelSelectionError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmRateLimitError,
    LlmStreamingDisabledError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
    LlmPlatformBoundaryError,
    _snapshot_json_object,
    _snapshot_json_value,
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


class LlmBatchState(StrEnum):
    """Provider-neutral lifecycle states for optional batch inference."""

    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class LlmBatchRequest:
    """Explicit batch boundary kept separate from interactive ModelRequest calls."""

    id: str
    requests: Sequence[ModelRequest]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or self.id.strip() == ""
            or not isinstance(self.requests, Sequence)
            or isinstance(self.requests, str | bytes)
            or len(self.requests) == 0
            or any(not isinstance(request, ModelRequest) for request in self.requests)
        ):
            raise LlmPlatformBoundaryError
        object.__setattr__(self, "requests", tuple(deepcopy(self.requests)))


@dataclass(frozen=True, slots=True)
class LlmBatchHandle:
    """Opaque provider batch handle without SDK objects."""

    id: str
    state: LlmBatchState

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or self.id.strip() == ""
            or not isinstance(self.state, LlmBatchState)
        ):
            raise LlmPlatformBoundaryError


class ILLMBatchProvider(ABC):
    """Optional batch port; interactive providers do not implement it implicitly."""

    @abstractmethod
    async def submit_batch(self, request: LlmBatchRequest) -> LlmBatchHandle:
        """Submit a backend-native asynchronous batch."""
        ...

    @abstractmethod
    async def batch_status(self, handle: LlmBatchHandle) -> LlmBatchHandle:
        """Read the current backend-native batch state."""
        ...

    @abstractmethod
    async def batch_results(self, handle: LlmBatchHandle) -> Sequence[ModelResponse]:
        """Return completed batch items in request order."""
        ...


@dataclass(frozen=True, slots=True)
class LlmFileUpload:
    """Explicit provider-native file payload outside ModelRequest messages."""

    name: str
    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or self.name.strip() == ""
            or not isinstance(self.media_type, str)
            or self.media_type.strip() == ""
            or not isinstance(self.content, bytes)
            or len(self.content) == 0
        ):
            raise LlmPlatformBoundaryError


@dataclass(frozen=True, slots=True)
class LlmFileHandle:
    """Opaque provider file reference scoped to its owning backend."""

    id: str
    name: str
    media_type: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or self.id.strip() == ""
            or not isinstance(self.name, str)
            or self.name.strip() == ""
            or not isinstance(self.media_type, str)
            or self.media_type.strip() == ""
        ):
            raise LlmPlatformBoundaryError


class ILLMFileProvider(ABC):
    """Optional file lifecycle port with no automatic upload or prompt injection."""

    @abstractmethod
    async def upload_file(self, upload: LlmFileUpload) -> LlmFileHandle:
        """Upload one file only when an application explicitly invokes this port."""
        ...

    @abstractmethod
    async def delete_file(self, handle: LlmFileHandle) -> None:
        """Delete one explicit provider-owned file."""
        ...


class LlmNativeToolKind(StrEnum):
    """Provider-native optional tools that are never Agent tool authority."""

    WEB_SEARCH = "web_search"
    FILE_SEARCH = "file_search"


@dataclass(frozen=True, slots=True)
class LlmNativeToolRequest:
    """Explicit native-tool request outside ModelRequest.tool_calling."""

    kind: LlmNativeToolKind
    arguments: JsonObject

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LlmNativeToolKind):
            raise LlmPlatformBoundaryError
        try:
            object.__setattr__(
                self,
                "arguments",
                _snapshot_json_object(self.arguments),
            )
        except LlmConfigurationError as error:
            raise LlmPlatformBoundaryError from error


@dataclass(frozen=True, slots=True)
class LlmNativeToolResult:
    """Provider-native tool result returned only through the optional port."""

    kind: LlmNativeToolKind
    output: JsonValue
    metadata: JsonObject

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LlmNativeToolKind):
            raise LlmPlatformBoundaryError
        try:
            object.__setattr__(self, "output", _snapshot_json_value(self.output))
            object.__setattr__(
                self,
                "metadata",
                _snapshot_json_object(self.metadata),
            )
        except LlmConfigurationError as error:
            raise LlmPlatformBoundaryError from error


class ILLMNativeToolProvider(ABC):
    """Optional native-tool port; providers never auto-execute it during inference."""

    @property
    @abstractmethod
    def native_tools(self) -> frozenset[LlmNativeToolKind]:
        """Return explicitly supported provider-native tool kinds."""
        ...

    @abstractmethod
    async def invoke_native_tool(
        self,
        request: LlmNativeToolRequest,
    ) -> LlmNativeToolResult:
        """Invoke one native tool only through this separate application boundary."""
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


def failure_code(error: AbstractLlmError) -> str:
    """Return the stable public code for one typed plugin failure."""
    if isinstance(error, LlmTimeoutError):
        return "llm_timeout"
    if isinstance(error, LlmTransportError):
        return "llm_transport_error"
    if isinstance(error, LlmRateLimitError):
        return "llm_rate_limited"
    if isinstance(error, LlmConcurrencyLimitError):
        return "llm_concurrency_limited"
    if isinstance(error, LlmCircuitOpenError):
        return "llm_circuit_open"
    if isinstance(error, LlmStreamingDisabledError):
        return "llm_streaming_disabled"
    if isinstance(error, LlmConfigurationError):
        return "llm_configuration_invalid"
    if isinstance(error, LlmCacheConfigurationError):
        return "llm_cache_invalid"
    if isinstance(error, LlmModelSelectionError):
        return "llm_model_selection_invalid"
    if isinstance(error, LlmProviderUnavailableError):
        return "llm_provider_unavailable"
    if isinstance(error, LlmCapabilityError):
        return "llm_capability_insufficient"
    if isinstance(error, LlmUnsupportedFeatureError):
        return "llm_feature_unsupported"
    if isinstance(error, LlmModelRefusalError):
        return "model_refusal"
    return "llm_response_error"


def to_model_error(error: AbstractLlmError, target: LlmModelTarget) -> ModelError:
    """Normalize one adapter exception for the public streaming error channel."""
    retryable = error.failure_class in {
        LlmFailureClass.TIMEOUT,
        LlmFailureClass.TRANSPORT,
        LlmFailureClass.RATE_LIMIT,
        LlmFailureClass.CONCURRENCY,
        LlmFailureClass.CIRCUIT_OPEN,
    }
    metadata: dict[str, JsonValue] = {
        **routing_metadata(target),
        "failure_class": error.failure_class.value,
        **error.details,
    }
    if error.retry_after_seconds is not None:
        metadata["retry_after_seconds"] = error.retry_after_seconds
    return ModelError(
        code=failure_code(error),
        message=error.message,
        retryable=retryable,
        metadata=metadata,
    )


def error_event(
    error: AbstractLlmError,
    target: LlmModelTarget,
    metadata: JsonObject | None = None,
) -> ModelStreamEvent:
    """Return one normalized terminal error event."""
    model_error = to_model_error(error, target)
    merged = {**model_error.metadata, **(metadata or {})}
    return ModelStreamEvent(
        kind=ModelStreamEventKind.ERROR,
        error=ModelError(
            code=model_error.code,
            message=model_error.message,
            retryable=model_error.retryable,
            metadata=merged,
        ),
        metadata=merged,
    )


def done_event(
    target: LlmModelTarget,
    finish_reason: str | None,
    usage: ModelUsage | None,
    metadata: JsonObject | None = None,
) -> ModelStreamEvent:
    """Return one provider-neutral terminal stream event."""
    return ModelStreamEvent(
        kind=ModelStreamEventKind.DONE,
        usage=usage,
        metadata={
            **routing_metadata(target),
            "finish_reason": finish_reason,
            **(metadata or {}),
        },
    )
