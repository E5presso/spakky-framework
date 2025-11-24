"""Error definitions for RabbitMQ plugin."""

from spakky.domain.models.event import AbstractDomainEvent


class DuplicateEventHandlerError(Exception):
    """Raised when attempting to register multiple handlers for the same event type."""

    def __init__(self, event_type: type[AbstractDomainEvent]) -> None:
        """Initialize with event type information.

        Args:
            event_type: The event type that already has a registered handler.
        """
        message = (
            f"Handler for event type '{event_type.__name__}' is already registered. "
            f"Multiple handlers for the same event type are not supported to avoid "
            f"duplicate processing on failure scenarios."
        )
        super().__init__(message)
        self.event_type = event_type
