"""Error definitions for RabbitMQ plugin."""

from spakky.core.error import AbstractSpakkyFrameworkError


class DuplicateEventHandlerError(AbstractSpakkyFrameworkError):
    """Raised when attempting to register multiple handlers for the same event type."""

    message = "Duplicate event handler registered for the same event type"


class InvalidMessageError(AbstractSpakkyFrameworkError):
    """Raised when a message received from RabbitMQ is invalid or malformed."""

    message = "Invalid or malformed message received from RabbitMQ"
