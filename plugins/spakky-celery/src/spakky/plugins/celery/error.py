"""Celery plugin error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyCeleryError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky Celery errors."""

    ...


class InvalidTimezoneError(AbstractSpakkyCeleryError):
    """Raised when an invalid IANA timezone string is provided."""

    message = "Invalid timezone"


class InvalidScheduleRouteError(AbstractSpakkyCeleryError):
    """Raised when a ScheduleRoute has no valid schedule specification."""

    message = "ScheduleRoute has no schedule specification"
