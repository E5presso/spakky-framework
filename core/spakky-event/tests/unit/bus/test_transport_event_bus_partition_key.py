"""Unit tests for partition key propagation from event bus to transport."""

from typing import override

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing import W3CTracePropagator

from spakky.event.bus.transport_event_bus import AsyncDirectEventBus, DirectEventBus
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@immutable
class UnkeyedIntegrationEvent(AbstractIntegrationEvent):
    """Integration event that leaves partition assignment to the broker."""

    message: str


@immutable
class OrderKeyedIntegrationEvent(AbstractIntegrationEvent):
    """Integration event pinned to the order it belongs to."""

    order_id: str

    @property
    @override
    def partition_key(self) -> str | None:
        """Return the order id so one order's events keep their order."""
        return self.order_id


class PartitionKeyRecordingTransport(IEventTransport):
    """Transport that records the partition key it was handed."""

    def __init__(self) -> None:
        self.partition_keys: list[str | None] = []

    @override
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.partition_keys.append(partition_key)

    @override
    def flush(self) -> None:
        """Nothing is buffered, so flushing is immediate."""


class AsyncPartitionKeyRecordingTransport(IAsyncEventTransport):
    """Async transport that records the partition key it was handed."""

    def __init__(self) -> None:
        self.partition_keys: list[str | None] = []

    @override
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.partition_keys.append(partition_key)

    @override
    async def flush(self) -> None:
        """Nothing is buffered, so flushing is immediate."""


def test_direct_event_bus_forwards_event_partition_key() -> None:
    """DirectEventBus가 이벤트의 partition_key를 transport에 전달함을 검증한다."""
    transport = PartitionKeyRecordingTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())

    bus.send(OrderKeyedIntegrationEvent(order_id="ORD-501"))

    assert transport.partition_keys == ["ORD-501"]


def test_direct_event_bus_forwards_none_for_unkeyed_event() -> None:
    """partition_key 미선언 이벤트는 transport에 None으로 전달됨을 검증한다."""
    transport = PartitionKeyRecordingTransport()
    bus = DirectEventBus(transport, W3CTracePropagator())

    bus.send(UnkeyedIntegrationEvent(message="hello"))

    assert transport.partition_keys == [None]


@pytest.mark.asyncio
async def test_async_direct_event_bus_forwards_event_partition_key() -> None:
    """AsyncDirectEventBus가 이벤트의 partition_key를 transport에 전달함을 검증한다."""
    transport = AsyncPartitionKeyRecordingTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())

    await bus.send(OrderKeyedIntegrationEvent(order_id="ORD-502"))

    assert transport.partition_keys == ["ORD-502"]


@pytest.mark.asyncio
async def test_async_direct_event_bus_forwards_none_for_unkeyed_event() -> None:
    """비동기 경로에서 partition_key 미선언 이벤트가 None으로 전달됨을 검증한다."""
    transport = AsyncPartitionKeyRecordingTransport()
    bus = AsyncDirectEventBus(transport, W3CTracePropagator())

    await bus.send(UnkeyedIntegrationEvent(message="hello"))

    assert transport.partition_keys == [None]
