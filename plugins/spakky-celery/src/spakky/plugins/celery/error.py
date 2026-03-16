"""Celery plugin error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyCeleryError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky Celery errors."""

    ...


class InvalidScheduleRouteError(AbstractSpakkyCeleryError):
    """Raised when a ScheduleRoute has no valid schedule specification."""

    message = "ScheduleRoute has no schedule specification"
