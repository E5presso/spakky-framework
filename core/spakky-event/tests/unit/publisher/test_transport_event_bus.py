"""Tests for DirectEventBus and AsyncDirectEventBus."""

import pytest
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing import W3CTracePropagator

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
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


class InMemoryAsyncTransport(IAsyncEventTransport):
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


def test_direct_event_bus_send_delegates_to_transport() -> None:
    """DirectEventBus.send가 transport에 이벤트를 위임하는지 검증한다."""
    transport = InMemorySyncTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())

    event = SampleIntegrationEvent(data="sync-test")
    bus.send(event)

    assert len(transport.sent) == 1
    event_name, payload, headers = transport.sent[0]
    assert event_name == "SampleIntegrationEvent"
    adapter: TypeAdapter[SampleIntegrationEvent] = TypeAdapter(SampleIntegrationEvent)
    assert payload == adapter.dump_json(event)


@pytest.mark.asyncio
async def test_async_direct_event_bus_send_delegates_to_transport() -> None:
    """AsyncDirectEventBus.send가 transport에 이벤트를 위임하는지 검증한다."""
    transport = InMemoryAsyncTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())

    event = SampleIntegrationEvent(data="async-test")
    await bus.send(event)

    assert len(transport.sent) == 1
    event_name, payload, headers = transport.sent[0]
    assert event_name == "SampleIntegrationEvent"
    adapter: TypeAdapter[SampleIntegrationEvent] = TypeAdapter(SampleIntegrationEvent)
    assert payload == adapter.dump_json(event)
