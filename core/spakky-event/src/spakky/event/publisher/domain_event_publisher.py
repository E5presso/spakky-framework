"""Event publisher implementations.

This module provides event publishers that route events by type:
- AbstractDomainEvent → EventMediator (in-process dispatch)
- AbstractIntegrationEvent → IEventBus (external transport)
"""

import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import (
    AbstractDomainEvent,
    AbstractEvent,
    AbstractIntegrationEvent,
)

from spakky.event.error import UnknownEventTypeError
from spakky.event.event_dispatcher import (
    IAsyncEventDispatcher,
    IEventDispatcher,
)
from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventPublisher,
    IEventBus,
    IEventPublisher,
)


@Pod()
class EventPublisher(IEventPublisher):
    """Routes events by type: domain events to dispatcher, integration events to bus."""

    _dispatcher: IEventDispatcher
    _bus: IEventBus

    def __init__(
        self,
        dispatcher: IEventDispatcher,
        bus: IEventBus,
    ) -> None:
        """Initialize with dispatcher and bus dependencies."""
        self._dispatcher = dispatcher
        self._bus = bus

    @override
    def publish(self, event: AbstractEvent) -> None:
        """Route an event to the appropriate handler based on its type."""
        match event:
            case AbstractDomainEvent():
                self._dispatcher.dispatch(event)
            case AbstractIntegrationEvent():
                self._bus.send(event)
            case _:  # pragma: no cover - 방어적 분기 (정상 흐름 불가)
                raise UnknownEventTypeError(type(event))


@Pod()
class AsyncEventPublisher(IAsyncEventPublisher):
    """Async counterpart that routes events by type."""

    _dispatcher: IAsyncEventDispatcher
    _bus: IAsyncEventBus

    def __init__(
        self,
        dispatcher: IAsyncEventDispatcher,
        bus: IAsyncEventBus,
    ) -> None:
        """Initialize with async dispatcher and bus dependencies."""
        self._dispatcher = dispatcher
        self._bus = bus

    @override
    async def publish(self, event: AbstractEvent) -> None:
        """Route an event to the appropriate async handler based on its type."""
        match event:
            case AbstractDomainEvent():
                await self._dispatcher.dispatch(event)
            case AbstractIntegrationEvent():
                await self._bus.send(event)
            case _:  # pragma: no cover - 방어적 분기 (정상 흐름 불가)
                raise UnknownEventTypeError(type(event))
