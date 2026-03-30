"""Tests for OutboxEventBus and AsyncOutboxEventBus."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing import W3CTracePropagator

from spakky.outbox.bus.outbox_event_bus import (
    AsyncOutboxEventBus,
    OutboxEventBus,
)
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage


@immutable
class OrderConfirmedIntegrationEvent(AbstractIntegrationEvent):
    order_id: str
    amount: int


class InMemorySyncOutboxStorage(IOutboxStorage):
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        raise AssertionError("Not expected to be called")

    def mark_published(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")

    def increment_retry(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")


class InMemoryAsyncOutboxStorage(IAsyncOutboxStorage):
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    async def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        raise AssertionError("Not expected to be called")

    async def mark_published(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")

    async def increment_retry(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")


# ── Sync OutboxEventBus ──


def test_send_stores_message_in_outbox_storage() -> None:
    """OutboxEventBus.send가 이벤트를 OutboxMessage로 변환하여 저장소에 저장하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-001", amount=5000)
    bus.send(event)

    assert len(storage.saved) == 1
    message = storage.saved[0]
    assert message.event_name == "OrderConfirmedIntegrationEvent"
    assert message.published_at is None
    assert message.retry_count == 0
    assert len(message.payload) > 0


def test_send_serializes_event_payload_as_json() -> None:
    """OutboxEventBus.send가 이벤트 payload를 JSON bytes로 직렬화하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-002", amount=3000)
    bus.send(event)

    message = storage.saved[0]
    payload_str = message.payload.decode("utf-8")
    assert "ORD-002" in payload_str
    assert "3000" in payload_str


def test_send_generates_unique_message_ids() -> None:
    """OutboxEventBus.send가 각 메시지에 고유한 ID를 부여하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event1 = OrderConfirmedIntegrationEvent(order_id="ORD-A", amount=100)
    event2 = OrderConfirmedIntegrationEvent(order_id="ORD-B", amount=200)
    bus.send(event1)
    bus.send(event2)

    assert len(storage.saved) == 2
    assert storage.saved[0].id != storage.saved[1].id


# ── Async AsyncOutboxEventBus ──


@pytest.mark.asyncio
async def test_async_send_stores_message_in_outbox_storage() -> None:
    """AsyncOutboxEventBus.send가 이벤트를 OutboxMessage로 변환하여 저장소에 저장하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-001", amount=5000)
    await bus.send(event)

    assert len(storage.saved) == 1
    message = storage.saved[0]
    assert message.event_name == "OrderConfirmedIntegrationEvent"
    assert message.published_at is None
    assert message.retry_count == 0
    assert len(message.payload) > 0


@pytest.mark.asyncio
async def test_async_send_serializes_event_payload_as_json() -> None:
    """AsyncOutboxEventBus.send가 이벤트 payload를 JSON bytes로 직렬화하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-002", amount=3000)
    await bus.send(event)

    message = storage.saved[0]
    payload_str = message.payload.decode("utf-8")
    assert "ORD-002" in payload_str
    assert "3000" in payload_str


@pytest.mark.asyncio
async def test_async_send_generates_unique_message_ids() -> None:
    """AsyncOutboxEventBus.send가 각 메시지에 고유한 ID를 부여하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event1 = OrderConfirmedIntegrationEvent(order_id="ORD-A", amount=100)
    event2 = OrderConfirmedIntegrationEvent(order_id="ORD-B", amount=200)
    await bus.send(event1)
    await bus.send(event2)

    assert len(storage.saved) == 2
    assert storage.saved[0].id != storage.saved[1].id
