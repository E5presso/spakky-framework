"""Subscriber identity shared by every integration event consumer.

A subscriber is one independent reader of an event stream. Each subscriber owns
its consume position, retry state and dead-letter destination, so one subscriber
failing or falling behind never affects another.
"""

from re import compile as compile_pattern
from typing import Final

from spakky.event.error import AbstractSpakkyEventError

type SubscriberName = str
"""Name of one independent subscriber; broker resources are derived from it."""

type HandlerName = str
"""Stable name of one handler inside a subscriber; part of the idempotency key."""

DEFAULT_SUBSCRIBER_KEY: Final = ""
"""Idempotency-key value recorded for handlers that declare no subscriber."""

SUBSCRIBER_NAME_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")
"""Names must stay valid inside Kafka group/topic names and RabbitMQ queue names.

A dot is excluded on purpose: brokers derive `<event>.<subscriber>.<suffix>`
resource names, and a dot inside the name would make them ambiguous.
"""


class InvalidSubscriberNameError(AbstractSpakkyEventError):
    """Raised when a subscriber name cannot be mapped onto broker resources."""

    message = "Subscriber name must match [A-Za-z0-9][A-Za-z0-9_-]{0,62}"
    subscriber: SubscriberName

    def __init__(self, subscriber: SubscriberName) -> None:
        self.subscriber = subscriber
        super().__init__()


class DuplicateEventHandlerNameError(AbstractSpakkyEventError):
    """Raised when two handlers of one subscription share a handler name."""

    message = "Handler name is already registered for this subscriber and event"
    subscriber: SubscriberName | None
    handler_name: HandlerName

    def __init__(
        self, subscriber: SubscriberName | None, handler_name: HandlerName
    ) -> None:
        self.subscriber = subscriber
        self.handler_name = handler_name
        super().__init__()


class MixedSubscriptionModeError(AbstractSpakkyEventError):
    """Raised when one subscription mixes sync and async handlers.

    Sync and async handlers are served by two separate consumers. Both would
    read the same broker subscription and split its messages between them, so
    each handler would silently miss part of the stream.
    """

    message = "Handlers of one subscriber for one event must be all sync or all async"
    subscriber: SubscriberName | None
    event_type: type

    def __init__(self, subscriber: SubscriberName | None, event_type: type) -> None:
        self.subscriber = subscriber
        self.event_type = event_type
        super().__init__()


class SubscriberNames:
    """Validation and key mapping for subscriber names."""

    @staticmethod
    def validate(subscriber: SubscriberName | None) -> SubscriberName | None:
        """Reject names that cannot be turned into broker resource names.

        Args:
            subscriber: Declared name, or None for the unnamed subscriber.

        Returns:
            The same value once it is known to be usable.

        Raises:
            InvalidSubscriberNameError: The name contains unsupported characters.
        """
        if subscriber is None:
            return None
        if SUBSCRIBER_NAME_PATTERN.fullmatch(subscriber) is None:
            raise InvalidSubscriberNameError(subscriber)
        return subscriber

    @staticmethod
    def key(subscriber: SubscriberName | None) -> SubscriberName:
        """Return the value stored for a subscriber in records and headers."""
        return DEFAULT_SUBSCRIBER_KEY if subscriber is None else subscriber
