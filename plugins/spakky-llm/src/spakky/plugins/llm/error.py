"""Errors raised by the multi-provider LLM plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractLlmError(AbstractSpakkyFrameworkError, ABC):
    """Base class for LLM routing and provider adapter failures."""

    ...


class LlmConfigurationError(AbstractLlmError):
    """Raised when configured profiles cannot form a valid provider registry."""

    message = "LLM provider configuration is invalid"


class LlmModelSelectionError(AbstractLlmError):
    """Raised when a request does not resolve to one allowlisted profile."""

    message = "LLM model selection is invalid"


class LlmProviderUnavailableError(AbstractLlmError):
    """Raised when no native SDK adapter exists for a selected profile API."""

    message = "LLM provider adapter is unavailable"


class LlmStreamingDisabledError(AbstractLlmError):
    """Raised when a selected profile disables streaming."""

    message = "LLM streaming is disabled for the selected profile"


class LlmTransportError(AbstractLlmError):
    """Raised when an official provider SDK cannot reach its endpoint."""

    message = "LLM provider transport request failed"


class LlmTimeoutError(AbstractLlmError):
    """Raised when an official provider SDK request times out."""

    message = "LLM provider request timed out"


class LlmResponseError(AbstractLlmError):
    """Raised when a provider response cannot satisfy Spakky contracts."""

    message = "LLM provider response is invalid"


class LlmModelRefusalError(AbstractLlmError):
    """Raised when a provider reports a model refusal or content filter."""

    message = "LLM model refused the request"


class LlmUnsupportedFeatureError(AbstractLlmError):
    """Raised when a selected provider cannot honor a requested feature."""

    message = "LLM provider cannot honor a requested feature"
