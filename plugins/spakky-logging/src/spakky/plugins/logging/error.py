"""Logging plugin error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyLoggingError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky Logging errors."""

    ...


class UnknownLogFormatError(AbstractSpakkyLoggingError):
    """Raised when an unrecognized log format is encountered."""

    message = "Unknown log format"
