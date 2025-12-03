"""Error classes for AOP-related exceptions."""

from abc import ABC

from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyAOPError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all AOP-related errors."""

    ...


class AspectInheritanceError(AbstractSpakkyAOPError):
    """Raised when an aspect class doesn't implement required interfaces.

    Aspect classes must inherit from either IAspect (for sync) or IAsyncAspect (for async).
    """

    message = "Aspect classes must inherit from either IAspect or IAsyncAspect"
