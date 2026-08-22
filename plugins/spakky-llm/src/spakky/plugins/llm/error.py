"""Errors raised by the multi-provider LLM plugin."""

from abc import ABC
from collections.abc import Mapping, Sequence
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import ClassVar

from spakky.agent import AbstractAgentModelError, JsonObject, JsonValue


class LlmFailureClass(StrEnum):
    """Provider-neutral failure classes used by retry and fallback policies."""

    CONFIGURATION = "configuration"
    SELECTION = "selection"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    STREAMING_DISABLED = "streaming_disabled"
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CONCURRENCY = "concurrency"
    CIRCUIT_OPEN = "circuit_open"
    RESPONSE = "response"
    REFUSAL = "refusal"
    CAPABILITY = "capability"
    UNSUPPORTED = "unsupported"
    CACHE = "cache"


class AbstractLlmError(AbstractAgentModelError, ABC):
    """Base class for LLM routing and provider adapter failures."""

    failure_class: ClassVar[LlmFailureClass] = LlmFailureClass.RESPONSE

    retry_after_seconds: float | None
    details: JsonObject

    def __init__(
        self,
        *,
        retry_after_seconds: float | None = None,
        details: JsonObject | None = None,
    ) -> None:
        super().__init__()
        if retry_after_seconds is not None and (
            not isfinite(retry_after_seconds) or retry_after_seconds < 0
        ):
            raise LlmConfigurationError
        self.retry_after_seconds = retry_after_seconds
        try:
            self.details = _snapshot_json_object({} if details is None else details)
        except RecursionError as error:
            raise LlmConfigurationError from error

    def annotate(self, details: JsonObject) -> None:
        """Attach privacy-safe orchestration evidence before propagation."""
        try:
            self.details = _snapshot_json_object({**self.details, **details})
        except RecursionError as error:
            raise LlmConfigurationError from error


class LlmConfigurationError(AbstractLlmError):
    """Raised when catalog, provider registry, client, or media policy is invalid."""

    message = "LLM provider configuration is invalid"
    failure_class = LlmFailureClass.CONFIGURATION


class LlmModelSelectionError(AbstractLlmError):
    """Raised when a request does not resolve to one catalog model ref."""

    message = "LLM model selection is invalid"
    failure_class = LlmFailureClass.SELECTION


class LlmProviderUnavailableError(AbstractLlmError):
    """Raised when no native SDK adapter exists for a selected profile API."""

    message = "LLM provider adapter is unavailable"
    failure_class = LlmFailureClass.PROVIDER_UNAVAILABLE


class LlmStreamingDisabledError(AbstractLlmError):
    """Raised when a selected profile disables streaming."""

    message = "LLM streaming is disabled for the selected profile"
    failure_class = LlmFailureClass.STREAMING_DISABLED


class LlmTransportError(AbstractLlmError):
    """Raised when an official provider SDK cannot reach its endpoint."""

    message = "LLM provider transport request failed"
    failure_class = LlmFailureClass.TRANSPORT


class LlmTimeoutError(AbstractLlmError):
    """Raised when an official provider SDK request times out."""

    message = "LLM provider request timed out"
    failure_class = LlmFailureClass.TIMEOUT


class LlmRateLimitError(AbstractLlmError):
    """Raised when a provider or local profile rate gate rejects an attempt."""

    message = "LLM provider rate limit was reached"
    failure_class = LlmFailureClass.RATE_LIMIT


class LlmConcurrencyLimitError(AbstractLlmError):
    """Raised when a profile concurrency gate cannot admit an attempt."""

    message = "LLM provider concurrency limit was reached"
    failure_class = LlmFailureClass.CONCURRENCY


class LlmCircuitOpenError(AbstractLlmError):
    """Raised while a profile circuit rejects calls before provider execution."""

    message = "LLM provider circuit is open"
    failure_class = LlmFailureClass.CIRCUIT_OPEN


class LlmResponseError(AbstractLlmError):
    """Raised when a provider response cannot satisfy Spakky contracts."""

    message = "LLM provider response is invalid"
    failure_class = LlmFailureClass.RESPONSE


class LlmModelRefusalError(AbstractLlmError):
    """Raised when a provider reports a model refusal or content filter."""

    message = "LLM model refused the request"
    failure_class = LlmFailureClass.REFUSAL


class LlmCapabilityError(AbstractLlmError):
    """Raised when no configured route can satisfy request capabilities."""

    message = "LLM model route capability is insufficient"
    failure_class = LlmFailureClass.CAPABILITY


class LlmUnsupportedFeatureError(AbstractLlmError):
    """Raised when a selected provider cannot honor a requested feature."""

    message = "LLM provider cannot honor a requested feature"
    failure_class = LlmFailureClass.UNSUPPORTED


class LlmCacheConfigurationError(AbstractLlmError):
    """Raised when an enabled cache mode has no exact replaceable backend."""

    message = "LLM response cache configuration is invalid"
    failure_class = LlmFailureClass.CACHE


class LlmPlatformBoundaryError(AbstractLlmError):
    """Raised for invalid optional batch, file, or native-tool requests."""

    message = "LLM platform boundary request is invalid"
    failure_class = LlmFailureClass.UNSUPPORTED


def _snapshot_json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise LlmConfigurationError
    return MappingProxyType(
        {
            key: _snapshot_json_value(item)
            for key, item in value.items()
            if _valid_json_key(key)
        }
    )


def _valid_json_key(value: object) -> bool:
    if not isinstance(value, str) or value == "":
        raise LlmConfigurationError
    return True


def _snapshot_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise LlmConfigurationError
        return value
    if isinstance(value, Mapping):
        return _snapshot_json_object(value)
    if isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    ):
        return tuple(_snapshot_json_value(item) for item in value)
    raise LlmConfigurationError
