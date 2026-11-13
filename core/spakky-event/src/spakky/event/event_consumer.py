"""Event consumer interfaces for registering event handlers."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from typing import override

from spakky.domain.models.event import AbstractEvent

from spakky.event.subscription import HandlerName, SubscriberName

type EventHandlerCallback[EventT_contra: AbstractEvent] = Callable[
    [EventT_contra], None
]
"""Synchronous event handler callback type."""
type AsyncEventHandlerCallback[EventT_contra: AbstractEvent] = Callable[
    [EventT_contra], Awaitable[None]
]
"""Asynchronous event handler callback type."""


class IEventConsumer(ABC):
    """Synchronous event consumer interface for registering event handlers."""

    @abstractmethod
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None:
        """Register a handler callback for the given event type."""
        ...


class IAsyncEventConsumer(ABC):
    """Asynchronous event consumer interface for registering event handlers."""

    @abstractmethod
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None:
        """Register an async handler callback for the given event type."""
        ...


class IDomainEventConsumer(IEventConsumer, ABC):
    """Synchronous provider that registers in-process domain event handlers."""


class IAsyncDomainEventConsumer(IAsyncEventConsumer, ABC):
    """Asynchronous provider that registers in-process domain event handlers."""


class IIntegrationEventConsumer(IEventConsumer, ABC):
    """Synchronous provider that registers external integration event handlers.

    Every implementation follows the delivery contract in
    `spakky.event.delivery`: subscribers read independently, every handler of a
    subscriber runs even when another fails, failed handlers are retried under
    the configured `RetryPolicy`, and exhausted messages move to the
    subscriber's own dead-letter destination.
    """

    @abstractmethod
    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register a handler in the subscription of `subscriber` for `event`.

        Args:
            event: Integration event type the handler receives.
            handler: Callback invoked with the deserialized event.
            subscriber: Independent subscriber the handler belongs to. None is
                the unnamed subscriber that reads through the consumer's base
                broker identity.
            handler_name: Name unique within the subscription; it is recorded in
                dead-letter metadata and in the idempotency key.
        """
        ...


class IAsyncIntegrationEventConsumer(IAsyncEventConsumer, ABC):
    """Asynchronous provider that registers external integration event handlers.

    Follows the same delivery contract as `IIntegrationEventConsumer`.
    """

    @abstractmethod
    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register an async handler in the subscription of `subscriber` for `event`.

        Args:
            event: Integration event type the handler receives.
            handler: Callback awaited with the deserialized event.
            subscriber: Independent subscriber the handler belongs to. None is
                the unnamed subscriber that reads through the consumer's base
                broker identity.
            handler_name: Name unique within the subscription; it is recorded in
                dead-letter metadata and in the idempotency key.
        """
        ...
