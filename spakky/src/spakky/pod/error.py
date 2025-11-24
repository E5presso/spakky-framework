"""Error types for Pod-related exceptions.

This module defines base error classes for Pod annotation and instantiation failures.
"""

from abc import ABC

from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyPodError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all Pod-related errors."""

    ...


class PodAnnotationFailedError(AbstractSpakkyPodError):
    """Raised when Pod annotation process fails."""

    message = "Pod annotation failed"


class PodInstantiationFailedError(AbstractSpakkyPodError):
    """Raised when Pod instantiation fails."""

    message = "Pod instantiation failed"
