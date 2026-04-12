"""Tests for OutboxRelayBackgroundService and AsyncOutboxRelayBackgroundService."""

import asyncio
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport

from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage
from spakky.outbox.relay.relay import (
    AsyncOutboxRelayBackgroundService,
    OutboxRelayBackgroundService,
)


@immutable
class RelayTestIntegrationEvent(AbstractIntegrationEvent):
    order_id: str


# ── Sync test doubles ──


class SpySyncTransport(IEventTransport):
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes]] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload))


class FailingSyncTransport(IEventTransport):
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        raise ConnectionError("Transport unavailable")


class InMemorySyncOutboxStorage(IOutboxStorage):
    def __init__(self, pending: list[OutboxMessage] | None = None) -> None:
        self.pending: list[OutboxMessage] = pending or []
        self.published_ids: list[object] = []
        self.retried_ids: list[object] = []

    def save(self, message: OutboxMessage) -> None:
        self.pending.append(message)

    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        return [
            m
            for m in self.pending
            if m.published_at is None and m.retry_count < max_retry
        ][:limit]

    def mark_published(self, message_id: object) -> None:
        self.published_ids.append(message_id)

    def increment_retry(self, message_id: object) -> None:
        self.retried_ids.append(message_id)


# ── Async test doubles ──


class SpyAsyncTransport(IAsyncEventTransport):
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes]] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload))


class FailingAsyncTransport(IAsyncEventTransport):
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        raise ConnectionError("Transport unavailable")


class InMemoryAsyncOutboxStorage(IAsyncOutboxStorage):
    def __init__(self, pending: list[OutboxMessage] | None = None) -> None:
        self.pending: list[OutboxMessage] = pending or []
        self.published_ids: list[object] = []
        self.retried_ids: list[object] = []

    async def save(self, message: OutboxMessage) -> None:
        self.pending.append(message)

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        return [
            m
            for m in self.pending
            if m.published_at is None and m.retry_count < max_retry
        ][:limit]

    async def mark_published(self, message_id: object) -> None:
        self.published_ids.append(message_id)

    async def increment_retry(self, message_id: object) -> None:
        self.retried_ids.append(message_id)


# ── Common helpers ──


def _make_message(event: AbstractIntegrationEvent) -> OutboxMessage:
    adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
    return OutboxMessage(
        id=uuid4(),
        event_name=event.event_name,
        payload=adapter.dump_json(event),
        headers={"traceparent": "00-abc123-def456-01"},
        created_at=datetime.now(UTC),
    )


def _make_config() -> OutboxConfig:
    os.environ["SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS"] = "0.01"
    os.environ["SPAKKY_OUTBOX__BATCH_SIZE"] = "10"
    os.environ["SPAKKY_OUTBOX__MAX_RETRY_COUNT"] = "3"
    try:
        return OutboxConfig()
    finally:
        del os.environ["SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS"]
        del os.environ["SPAKKY_OUTBOX__BATCH_SIZE"]
        del os.environ["SPAKKY_OUTBOX__MAX_RETRY_COUNT"]


# ── Sync OutboxRelayBackgroundService tests ──


def test_relay_batch_publishes_raw_payload_to_transport() -> None:
    """_relay_batch가 미발행 메시지의 raw payload를 Transport로 전달하는지 검증한다."""
    event = RelayTestIntegrationEvent(order_id="ORD-100")
    message = _make_message(event)

    storage = InMemorySyncOutboxStorage(pending=[message])
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    relay._relay_batch()

    assert len(transport.sent) == 1
    event_name, payload = transport.sent[0]
    assert event_name == "RelayTestIntegrationEvent"
    assert payload == message.payload
    assert message.id in storage.published_ids


def test_relay_batch_increments_retry_on_transport_failure() -> None:
    """Transport 전송 실패 시 _relay_batch가 retry count를 증가시키는지 검증한다."""
    event = RelayTestIntegrationEvent(order_id="ORD-FAIL")
    message = _make_message(event)

    storage = InMemorySyncOutboxStorage(pending=[message])
    transport = FailingSyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    relay._relay_batch()

    assert len(storage.published_ids) == 0
    assert message.id in storage.retried_ids


def test_relay_run_stops_on_stop_event() -> None:
    """run이 stop_event 설정 시 정상 종료하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    stop_event = threading.Event()
    relay.set_stop_event(stop_event)
    stop_event.set()
    relay.run()


# ── Async AsyncOutboxRelayBackgroundService tests ──


@pytest.mark.asyncio
async def test_async_relay_batch_publishes_raw_payload_to_transport() -> None:
    """_relay_batch가 미발행 메시지의 raw payload를 Transport로 전달하는지 검증한다."""
    event = RelayTestIntegrationEvent(order_id="ORD-100")
    message = _make_message(event)

    storage = InMemoryAsyncOutboxStorage(pending=[message])
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    await relay._relay_batch()

    assert len(transport.sent) == 1
    event_name, payload = transport.sent[0]
    assert event_name == "RelayTestIntegrationEvent"
    assert payload == message.payload
    assert message.id in storage.published_ids


@pytest.mark.asyncio
async def test_async_relay_batch_increments_retry_on_transport_failure() -> None:
    """Transport 전송 실패 시 _relay_batch가 retry count를 증가시키는지 검증한다."""
    event = RelayTestIntegrationEvent(order_id="ORD-FAIL")
    message = _make_message(event)

    storage = InMemoryAsyncOutboxStorage(pending=[message])
    transport = FailingAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    await relay._relay_batch()

    assert len(storage.published_ids) == 0
    assert message.id in storage.retried_ids


@pytest.mark.asyncio
async def test_async_relay_run_async_stops_on_stop_event() -> None:
    """run_async가 stop_event 설정 시 정상 종료하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    stop_event = asyncio.Event()
    relay.set_stop_event(stop_event)

    async def stop_after_delay() -> None:
        await asyncio.sleep(0.05)
        stop_event.set()

    task = asyncio.create_task(stop_after_delay())
    await relay.run_async()
    await task


# ── Lifecycle method tests ──


def test_relay_initialize_returns_none() -> None:
    """Sync relay의 initialize가 None을 반환하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    assert relay.initialize() is None


def test_relay_dispose_returns_none() -> None:
    """Sync relay의 dispose가 None을 반환하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    assert relay.dispose() is None


@pytest.mark.asyncio
async def test_async_relay_initialize_async_returns_none() -> None:
    """Async relay의 initialize_async가 None을 반환하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    assert await relay.initialize_async() is None


@pytest.mark.asyncio
async def test_async_relay_dispose_async_returns_none() -> None:
    """Async relay의 dispose_async가 None을 반환하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    assert await relay.dispose_async() is None


@pytest.mark.asyncio
async def test_async_relay_run_async_exits_immediately_when_already_stopped() -> None:
    """stop_event가 이미 set되어 있으면 run_async가 즉시 반환하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    stop_event = asyncio.Event()
    stop_event.set()
    relay.set_stop_event(stop_event)

    await relay.run_async()

    assert len(transport.sent) == 0
