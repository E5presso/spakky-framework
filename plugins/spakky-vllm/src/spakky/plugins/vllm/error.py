"""Error classes for the spakky-vllm plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractVllmError(AbstractSpakkyFrameworkError, ABC):
    """Base class for vLLM adapter errors."""

    ...


class VllmTransportError(AbstractVllmError):
    """Raised when the OpenAI-compatible vLLM endpoint cannot be reached."""

    message = "vLLM transport request failed"


class VllmTimeoutError(AbstractVllmError):
    """Raised when the OpenAI-compatible vLLM endpoint times out."""

    message = "vLLM request timed out"


class VllmResponseError(AbstractVllmError):
    """Raised when a vLLM response cannot be mapped to Spakky model contracts."""

    message = "vLLM response is invalid"


class VllmStreamingDisabledError(AbstractVllmError):
    """Raised when streaming is disabled by plugin configuration."""

    message = "vLLM streaming is disabled"


class VllmModelRefusalError(AbstractVllmError):
    """Raised when the model refuses to produce a normal completion."""

    message = "vLLM model refused the request"


class VllmStreamingNotImplementedError(AbstractVllmError):
    """Backward-compatible alias for pre-streaming adapter failures."""

    message = "vLLM streaming mapper is not implemented yet"
