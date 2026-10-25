from abc import ABC
from math import isfinite

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyEventError(AbstractSpakkyFrameworkError, ABC):
    """Base error for event system operations."""


class InvalidMessageError(AbstractSpakkyEventError):
    """Raised when a message received is invalid or malformed."""

    message = "Invalid or malformed message received"


class IntegrationEventTransportUnavailableError(AbstractSpakkyEventError):
    """Raised when integration events are published without a broker transport."""

    message = "Integration event publishing requires an event transport plugin"


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


class EventDeliveryRejectedError(AbstractSpakkyEventError):
    """Raised when a transport attributes a permanent rejection to a record.

    A client may report the rejection synchronously from send() or later through
    a delivery callback consumed by flush(). Both paths use this error so callers
    can distinguish record-specific failure from a transport-wide outage.
    """

    message = "Broker rejected event delivery"

    reasons: list[str]

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__()


class UnknownEventTypeError(AbstractSpakkyEventError):
    """Raised when an event type is neither domain nor integration."""

    message = "Unknown event type"

    event_type: type

    def __init__(self, event_type: type) -> None:
        self.event_type = event_type
        super().__init__()


class InvalidEventDeferralError(AbstractSpakkyEventError):
    """Raised when a deferral delay is not finite and strictly positive."""

    message = "Event deferral requires a finite positive retry delay"


class EventDeferredError(AbstractSpakkyEventError):
    """Defer delivery without counting a handler failure or acknowledging it.

    Raise before effects, or let a transaction roll back before this reaches the
    consumer. Earlier handlers may run again and must remain idempotent. Broker
    consumers supporting deferral retry after the delay while continuing to poll.
    Direct in-process dispatch propagates the error to its caller.
    """

    message = "Event delivery is temporarily deferred"
    retry_after: float

    def __init__(self, retry_after: float = 1.0) -> None:
        if not isfinite(retry_after) or retry_after <= 0:
            raise InvalidEventDeferralError()
        self.retry_after = retry_after
        super().__init__()
