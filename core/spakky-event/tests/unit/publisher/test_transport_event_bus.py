"""Tests for DirectEventBus and AsyncDirectEventBus."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.bus.transport_event_bus import (
    AsyncDirectEventBus,
    DirectEventBus,
)
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    data: str


class InMemorySyncTransport(IEventTransport):
    def __init__(self) -> None:
        self.sent: list[AbstractIntegrationEvent] = []

    def send(self, event: AbstractIntegrationEvent) -> None:
        self.sent.append(event)


class InMemoryAsyncTransport(IAsyncEventTransport):
    def __init__(self) -> None:
        self.sent: list[AbstractIntegrationEvent] = []

    async def send(self, event: AbstractIntegrationEvent) -> None:
        self.sent.append(event)


def test_direct_event_bus_send_delegates_to_transport() -> None:
    """DirectEventBus.send가 transport에 이벤트를 위임하는지 검증한다."""
    transport = InMemorySyncTransport()
    bus = DirectEventBus(transport)

    event = SampleIntegrationEvent(data="sync-test")
    bus.send(event)

    assert len(transport.sent) == 1
    assert transport.sent[0] is event


@pytest.mark.asyncio
async def test_async_direct_event_bus_send_delegates_to_transport() -> None:
    """AsyncDirectEventBus.send가 transport에 이벤트를 위임하는지 검증한다."""
    transport = InMemoryAsyncTransport()
    bus = AsyncDirectEventBus(transport)

    event = SampleIntegrationEvent(data="async-test")
    await bus.send(event)

    assert len(transport.sent) == 1
    assert transport.sent[0] is event
