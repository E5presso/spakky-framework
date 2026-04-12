from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyEventError(AbstractSpakkyFrameworkError, ABC):
    """Base error for event system operations."""


class InvalidMessageError(AbstractSpakkyEventError):
    """Raised when a message received is invalid or malformed."""

    message = "Invalid or malformed message received"


class UnknownEventTypeError(AbstractSpakkyEventError):
    """Raised when an event type is neither domain nor integration."""

    message = "Unknown event type"

    event_type: type

    def __init__(self, event_type: type) -> None:
        self.event_type = event_type
        super().__init__()
