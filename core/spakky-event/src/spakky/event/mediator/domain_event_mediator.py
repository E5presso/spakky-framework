"""Domain event mediator implementations.

This module provides in-process mediator implementations that combine Consumer
and Dispatcher interfaces. Mediators manage handler registration and event
dispatching within the same bounded context.

Usage:
    from spakky.event.mediator import AsyncDomainEventMediator

    mediator = AsyncDomainEventMediator()
    mediator.register(UserCreatedEvent, handle_user_created)
    await mediator.dispatch(event)
"""

from logging import getLogger
from typing import Any

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.event_consumer import (
    AsyncDomainEventHandlerCallback,
    DomainEventHandlerCallback,
    IAsyncDomainEventConsumer,
    IDomainEventConsumer,
)
from spakky.event.event_dispatcher import (
    IAsyncDomainEventDispatcher,
    IDomainEventDispatcher,
)

logger = getLogger(__name__)


@Pod()
class DomainEventMediator(IDomainEventConsumer, IDomainEventDispatcher):
    """In-process synchronous domain event mediator.

    Combines Consumer (handler registration) and Dispatcher (event delivery)
    responsibilities for synchronous event handling within the same process.

    Attributes:
        _handlers: Registry mapping event types to their handlers.
    """

    _handlers: dict[type[AbstractDomainEvent], list[DomainEventHandlerCallback[Any]]]

    def __init__(self) -> None:
        """Initialize empty handler registry."""
        self._handlers = {}

    def register(
        self,
        event: type[AbstractDomainEvent],
        handler: DomainEventHandlerCallback[Any],
    ) -> None:
        """Register a handler for a domain event type.

        Multiple handlers can be registered for the same event type.
        Handlers are called in registration order (FIFO).

        Args:
            event: The domain event type to handle.
            handler: The callback function to invoke when event is dispatched.
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug(f"Registered handler for {event.__name__}")

    def dispatch(self, event: AbstractDomainEvent) -> None:
        """Dispatch a domain event to all registered handlers.

        All handlers for the event type are invoked in registration order.
        If a handler raises an exception, it is logged but remaining handlers
        continue to execute (resilient dispatch).

        Args:
            event: The domain event to dispatch.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(f"No handlers registered for {event_type.__name__}")
            return

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Handler {handler} failed for {event_type.__name__}: {e}",
                    exc_info=True,
                )


@Pod()
class AsyncDomainEventMediator(IAsyncDomainEventConsumer, IAsyncDomainEventDispatcher):
    """In-process asynchronous domain event mediator.

    Combines Consumer (handler registration) and Dispatcher (event delivery)
    responsibilities for asynchronous event handling within the same process.

    Attributes:
        _handlers: Registry mapping event types to their async handlers.
    """

    _handlers: dict[
        type[AbstractDomainEvent], list[AsyncDomainEventHandlerCallback[Any]]
    ]

    def __init__(self) -> None:
        """Initialize empty handler registry."""
        self._handlers = {}

    def register(
        self,
        event: type[AbstractDomainEvent],
        handler: AsyncDomainEventHandlerCallback[Any],
    ) -> None:
        """Register an async handler for a domain event type.

        Multiple handlers can be registered for the same event type.
        Handlers are called in registration order (FIFO).

        Args:
            event: The domain event type to handle.
            handler: The async callback function to invoke when event is dispatched.
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug(f"Registered async handler for {event.__name__}")

    async def dispatch(self, event: AbstractDomainEvent) -> None:
        """Dispatch a domain event to all registered async handlers.

        All handlers for the event type are invoked in registration order.
        If a handler raises an exception, it is logged but remaining handlers
        continue to execute (resilient dispatch).

        Args:
            event: The domain event to dispatch.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(f"No handlers registered for {event_type.__name__}")
            return

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    f"Handler {handler} failed for {event_type.__name__}: {e}",
                    exc_info=True,
                )
