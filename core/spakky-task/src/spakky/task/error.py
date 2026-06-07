"""Spakky Task error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyTaskError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all spakky-task errors."""

    ...


class TaskNotFoundError(AbstractSpakkyTaskError):
    """Raised when a task reference cannot be found in the registry."""

    message = "Task not found in the registry"


class TaskApplicationContextNotFoundError(AbstractSpakkyTaskError):
    """Raised when direct task execution has no ApplicationContext."""

    message = "ApplicationContext is required for direct task execution"


class TaskAsyncInvocationRequiredError(AbstractSpakkyTaskError):
    """Raised when an async task is invoked through the sync direct path."""

    message = "Async task requires execute_async for direct execution"


class DuplicateTaskError(AbstractSpakkyTaskError):
    """Raised when attempting to register a task that already exists."""

    message = "Duplicate task registered"


class InvalidScheduleSpecificationError(AbstractSpakkyTaskError):
    """Raised when a ScheduleRoute has invalid schedule options."""

    message = "Exactly one of 'interval', 'at', or 'crontab' must be provided"
