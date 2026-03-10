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

    def __init__(self, transport: IEventTransport) -> None:
        self._transport = transport

    def send(self, event: AbstractIntegrationEvent) -> None:
        adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
        self._transport.send(event.event_name, adapter.dump_json(event))


@Pod()
class AsyncDirectEventBus(IAsyncEventBus):
    _transport: IAsyncEventTransport

    def __init__(self, transport: IAsyncEventTransport) -> None:
        self._transport = transport

    async def send(self, event: AbstractIntegrationEvent) -> None:
        adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
        await self._transport.send(event.event_name, adapter.dump_json(event))
