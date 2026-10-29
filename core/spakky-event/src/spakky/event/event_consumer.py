"""Event consumer interfaces for registering event handlers."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from spakky.domain.models.event import AbstractEvent

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
    """Synchronous provider that registers external integration event handlers."""


class IAsyncIntegrationEventConsumer(IAsyncEventConsumer, ABC):
    """Asynchronous provider that registers external integration event handlers."""
