from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyEventError(AbstractSpakkyFrameworkError, ABC): ...


class DuplicateEventHandlerError(AbstractSpakkyEventError):
    """Raised when attempting to register multiple handlers for the same event type."""

    message = "Duplicate event handler registered for the same event type"


class InvalidMessageError(AbstractSpakkyEventError):
    """Raised when a message received is invalid or malformed."""

    message = "Invalid or malformed message received"
