"""Event mediator implementations.

This module provides in-process mediator implementations that combine Consumer
and Dispatcher interfaces. Mediators manage handler registration and event
dispatching within the same bounded context.
"""

from logging import getLogger
from typing import Any

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractEvent

from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.event_dispatcher import (
    IAsyncEventDispatcher,
    IEventDispatcher,
)

logger = getLogger(__name__)


@Pod()
class EventMediator(IEventConsumer, IEventDispatcher):
    _handlers: dict[type[AbstractEvent], list[EventHandlerCallback[Any]]]

    def __init__(self) -> None:
        self._handlers = {}

    def register(
        self,
        event: type[AbstractEvent],
        handler: EventHandlerCallback[Any],
    ) -> None:
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug(f"Registered handler for {event.__name__}")

    def dispatch(self, event: AbstractEvent) -> None:
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
class AsyncEventMediator(IAsyncEventConsumer, IAsyncEventDispatcher):
    _handlers: dict[type[AbstractEvent], list[AsyncEventHandlerCallback[Any]]]

    def __init__(self) -> None:
        self._handlers = {}

    def register(
        self,
        event: type[AbstractEvent],
        handler: AsyncEventHandlerCallback[Any],
    ) -> None:
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug(f"Registered async handler for {event.__name__}")

    async def dispatch(self, event: AbstractEvent) -> None:
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
