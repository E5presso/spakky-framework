"""Error classes for the spakky-vllm plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractVllmError(AbstractSpakkyFrameworkError, ABC):
    """Base class for vLLM adapter errors."""

    ...


class VllmTransportError(AbstractVllmError):
    """Raised when the OpenAI-compatible vLLM endpoint cannot be reached."""

    message = "vLLM transport request failed"


class VllmResponseError(AbstractVllmError):
    """Raised when a vLLM response cannot be mapped to Spakky model contracts."""

    message = "vLLM response is invalid"


class VllmStreamingNotImplementedError(AbstractVllmError):
    """Raised until the streaming mapper lands in the dedicated follow-up."""

    message = "vLLM streaming mapper is not implemented yet"
