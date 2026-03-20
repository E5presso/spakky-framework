"""Error classes for the spakky-tracing package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyTracingError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all tracing-related errors."""

    ...


class InvalidTraceparentError(AbstractSpakkyTracingError):
    """Raised when a traceparent header has an invalid format."""

    message = "Invalid traceparent header format"
