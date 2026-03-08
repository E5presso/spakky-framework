"""Event publisher implementations.

This module provides event publishers that route events by type:
- AbstractDomainEvent → EventMediator (in-process dispatch)
- AbstractIntegrationEvent → IEventBus (external transport)
"""

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import (
    AbstractDomainEvent,
    AbstractEvent,
    AbstractIntegrationEvent,
)

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
    _dispatcher: IEventDispatcher
    _bus: IEventBus

    def __init__(
        self,
        dispatcher: IEventDispatcher,
        bus: IEventBus,
    ) -> None:
        self._dispatcher = dispatcher
        self._bus = bus

    def publish(self, event: AbstractEvent) -> None:
        match event:
            case AbstractDomainEvent():
                self._dispatcher.dispatch(event)
            case AbstractIntegrationEvent():
                self._bus.send(event)
            case _:  # pragma: no cover - 방어적 분기 (정상 흐름 불가)
                raise AssertionError(f"Unknown event type: {type(event)!r}")


@Pod()
class AsyncEventPublisher(IAsyncEventPublisher):
    _dispatcher: IAsyncEventDispatcher
    _bus: IAsyncEventBus

    def __init__(
        self,
        dispatcher: IAsyncEventDispatcher,
        bus: IAsyncEventBus,
    ) -> None:
        self._dispatcher = dispatcher
        self._bus = bus

    async def publish(self, event: AbstractEvent) -> None:
        match event:
            case AbstractDomainEvent():
                await self._dispatcher.dispatch(event)
            case AbstractIntegrationEvent():
                await self._bus.send(event)
            case _:  # pragma: no cover - 방어적 분기 (정상 흐름 불가)
                raise AssertionError(f"Unknown event type: {type(event)!r}")
