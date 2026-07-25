"""Unit tests for DirectEventBus and AsyncDirectEventBus."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing import W3CTracePropagator

from spakky.event.bus.transport_event_bus import AsyncDirectEventBus, DirectEventBus
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for testing."""

    message: str


class RecordingTransport(IEventTransport):
    """Transport that records sent events and flush calls."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []
        self.flush_count: int = 0

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.sent.append((event_name, payload, headers))

    def flush(self) -> None:
        self.flush_count += 1


class AsyncRecordingTransport(IAsyncEventTransport):
    """Async transport that records sent events and flush calls."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []
        self.flush_count: int = 0

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.sent.append((event_name, payload, headers))

    async def flush(self) -> None:
        self.flush_count += 1


def test_direct_event_bus_send_single_expect_transport_called() -> None:
    """DirectEventBus.send가 transport.send를 호출함을 검증한다."""
    transport = RecordingTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())
    event = SampleIntegrationEvent(message="hello")

    bus.send(event)

    assert len(transport.sent) == 1
    assert transport.sent[0][0] == "SampleIntegrationEvent"


def test_direct_event_bus_send_same_type_twice_expect_adapter_cached() -> None:
    """동일 이벤트 타입 재전송 시 TypeAdapter가 캐시됨을 검증한다."""
    transport = RecordingTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())
    event1 = SampleIntegrationEvent(message="first")
    event2 = SampleIntegrationEvent(message="second")

    bus.send(event1)
    bus.send(event2)

    assert len(transport.sent) == 2
    assert SampleIntegrationEvent in bus._adapters
    assert len(bus._adapters) == 1


@pytest.mark.asyncio
async def test_async_direct_event_bus_send_single_expect_transport_called() -> None:
    """AsyncDirectEventBus.send가 async transport.send를 호출함을 검증한다."""
    transport = AsyncRecordingTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())
    event = SampleIntegrationEvent(message="hello")

    await bus.send(event)

    assert len(transport.sent) == 1
    assert transport.sent[0][0] == "SampleIntegrationEvent"


@pytest.mark.asyncio
async def test_async_direct_event_bus_send_same_type_twice_expect_adapter_cached() -> (
    None
):
    """동일 이벤트 타입 재전송 시 TypeAdapter가 캐시됨을 검증한다."""
    transport = AsyncRecordingTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())
    event1 = SampleIntegrationEvent(message="first")
    event2 = SampleIntegrationEvent(message="second")

    await bus.send(event1)
    await bus.send(event2)

    assert len(transport.sent) == 2
    assert SampleIntegrationEvent in bus._adapters
    assert len(bus._adapters) == 1


def test_direct_event_bus_send_expect_transport_flushed_once_per_event() -> None:
    """DirectEventBus.send가 발행 1건마다 transport.flush를 한 번 호출함을 검증한다."""
    transport = RecordingTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())

    bus.send(SampleIntegrationEvent(message="first"))
    bus.send(SampleIntegrationEvent(message="second"))

    assert transport.flush_count == 2


@pytest.mark.asyncio
async def test_async_direct_event_bus_send_expect_transport_flushed_once_per_event() -> (
    None
):
    """AsyncDirectEventBus.send가 발행 1건마다 transport.flush를 한 번 호출함을 검증한다."""
    transport = AsyncRecordingTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())

    await bus.send(SampleIntegrationEvent(message="first"))
    await bus.send(SampleIntegrationEvent(message="second"))

    assert transport.flush_count == 2
