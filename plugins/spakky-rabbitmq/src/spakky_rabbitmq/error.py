"""Error definitions for RabbitMQ plugin."""

from spakky.core.error import AbstractSpakkyFrameworkError
from spakky.domain.models.event import AbstractDomainEvent


class DuplicateEventHandlerError(AbstractSpakkyFrameworkError):
    """Raised when attempting to register multiple handlers for the same event type."""

    def __init__(self, event_type: type[AbstractDomainEvent]) -> None:
        """Initialize with event type information.

        Args:
            event_type: The event type that already has a registered handler.
        """
        self.message = (
            f"Handler for event type '{event_type.__name__}' is already registered. "
            f"Multiple handlers for the same event type are not supported to avoid "
            f"duplicate processing on failure scenarios."
        )
        self.event_type = event_type


class InvalidMessageError(AbstractSpakkyFrameworkError):
    """Raised when a message received from RabbitMQ is invalid or malformed."""

    def __init__(self, details: str) -> None:
        """Initialize with error details.

        Args:
            details: Description of why the message is considered invalid.
        """
        self.message = f"Invalid message received from RabbitMQ: {details}"
        self.details = details
