"""Default EventBus implementations that delegate to EventTransport."""

from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventTransport,
    IEventBus,
    IEventTransport,
)


@Pod()
class DirectEventBus(IEventBus):
    _transport: IEventTransport
    _adapters: dict[type, TypeAdapter[AbstractIntegrationEvent]]

    def __init__(self, transport: IEventTransport) -> None:
        self._transport = transport
        self._adapters = {}

    def send(self, event: AbstractIntegrationEvent) -> None:
        event_type = type(event)
        if event_type not in self._adapters:
            self._adapters[event_type] = TypeAdapter(event_type)
        adapter = self._adapters[event_type]
        self._transport.send(event.event_name, adapter.dump_json(event))


@Pod()
class AsyncDirectEventBus(IAsyncEventBus):
    _transport: IAsyncEventTransport
    _adapters: dict[type, TypeAdapter[AbstractIntegrationEvent]]

    def __init__(self, transport: IAsyncEventTransport) -> None:
        self._transport = transport
        self._adapters = {}

    async def send(self, event: AbstractIntegrationEvent) -> None:
        event_type = type(event)
        if event_type not in self._adapters:
            self._adapters[event_type] = TypeAdapter(event_type)
        adapter = self._adapters[event_type]
        await self._transport.send(event.event_name, adapter.dump_json(event))
