from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyEventError(AbstractSpakkyFrameworkError, ABC):
    """Base error for event system operations."""


class InvalidMessageError(AbstractSpakkyEventError):
    """Raised when a message received is invalid or malformed."""

    message = "Invalid or malformed message received"


class AuthSnapshotPropagationSignerUnavailableError(AbstractSpakkyEventError):
    """Raised when signed snapshot propagation lacks a signer provider."""

    message = "Auth snapshot propagation signer is unavailable"


class AuthSnapshotPropagationContextUnavailableError(AbstractSpakkyEventError):
    """Raised when signed snapshot propagation cannot read ApplicationContext."""

    message = "Auth snapshot propagation context is unavailable"


class EventTransportNotRunningError(AbstractSpakkyEventError):
    """Raised when a transport is used outside the application lifecycle.

    Transports whose broker client is opened at application start and closed at
    application stop raise this instead of publishing into a closed client, so
    that callers can tell a shutdown window apart from a delivery failure.
    """

    message = "Event transport is not running"


class UnknownEventTypeError(AbstractSpakkyEventError):
    """Raised when an event type is neither domain nor integration."""

    message = "Unknown event type"

    event_type: type

    def __init__(self, event_type: type) -> None:
        self.event_type = event_type
        super().__init__()
