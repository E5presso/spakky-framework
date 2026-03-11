"""Spakky Task error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyTaskError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all spakky-task errors."""

    ...


class TaskNotFoundError(AbstractSpakkyTaskError):
    """Raised when a task reference cannot be found in the registry."""

    message = "Task not found in the registry"


class DuplicateTaskError(AbstractSpakkyTaskError):
    """Raised when attempting to register a task that already exists."""

    message = "Duplicate task registered"
