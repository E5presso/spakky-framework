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
from spakky.event.error import EventTransportNotRunningError
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
        self.partition_keys: list[str | None] = []
        self.flush_marks: list[int] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.sent.append((event_name, payload))
        self.partition_keys.append(partition_key)

    def flush(self) -> None:
        self.flush_marks.append(len(self.sent))


class FailingSyncTransport(IEventTransport):
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        raise ConnectionError("Transport unavailable")

    def flush(self) -> None:
        """Never reached: send fails before the batch is flushed."""


class FailingFlushSyncTransport(IEventTransport):
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Accept the payload; the failure happens when the batch is flushed."""

    def flush(self) -> None:
        raise ConnectionError("Broker unreachable")


class StoppedSyncTransport(IEventTransport):
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        raise EventTransportNotRunningError

    def flush(self) -> None:
        """Never reached: the transport refuses the batch at the first send."""


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
        self.partition_keys: list[str | None] = []
        self.flush_marks: list[int] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.sent.append((event_name, payload))
        self.partition_keys.append(partition_key)

    async def flush(self) -> None:
        self.flush_marks.append(len(self.sent))


class FailingAsyncTransport(IAsyncEventTransport):
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        raise ConnectionError("Transport unavailable")

    async def flush(self) -> None:
        """Never reached: send fails before the batch is flushed."""


class FailingFlushAsyncTransport(IAsyncEventTransport):
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Accept the payload; the failure happens when the batch is flushed."""

    async def flush(self) -> None:
        raise ConnectionError("Broker unreachable")


class StoppedAsyncTransport(IAsyncEventTransport):
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        raise EventTransportNotRunningError

    async def flush(self) -> None:
        """Never reached: the transport refuses the batch at the first send."""


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


def _make_message(
    event: AbstractIntegrationEvent,
    partition_key: str | None = None,
) -> OutboxMessage:
    adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
    return OutboxMessage(
        id=uuid4(),
        event_name=event.event_name,
        payload=adapter.dump_json(event),
        headers={"traceparent": "00-abc123-def456-01"},
        partition_key=partition_key,
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


def test_relay_batch_with_three_messages_expect_single_flush_after_last_send() -> None:
    """배치 전체를 보낸 뒤 flush를 한 번만 호출하고 그 후 발행 완료로 표시한다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(3)
    ]

    storage = InMemorySyncOutboxStorage(pending=messages)
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    relay._relay_batch()

    assert transport.flush_marks == [3]
    assert storage.published_ids == [message.id for message in messages]


def test_relay_batch_flush_failure_expect_batch_left_pending_without_retry_charge() -> (
    None
):
    """배치 flush가 실패하면 발행 완료로 표시하지 않고 retry count도 올리지 않는다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(2)
    ]

    storage = InMemorySyncOutboxStorage(pending=messages)
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, FailingFlushSyncTransport(), config)
    relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []


def test_relay_batch_transport_stopped_expect_batch_left_pending_without_retry_charge() -> (
    None
):
    """종료로 transport가 닫히면 배치를 그대로 두고 retry count를 올리지 않는다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(3)
    ]

    storage = InMemorySyncOutboxStorage(pending=messages)
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, StoppedSyncTransport(), config)
    relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []


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
async def test_async_relay_batch_with_three_messages_expect_single_flush_after_last_send() -> (
    None
):
    """배치 전체를 보낸 뒤 flush를 한 번만 호출하고 그 후 발행 완료로 표시한다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(3)
    ]

    storage = InMemoryAsyncOutboxStorage(pending=messages)
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    await relay._relay_batch()

    assert transport.flush_marks == [3]
    assert storage.published_ids == [message.id for message in messages]


@pytest.mark.asyncio
async def test_async_relay_batch_flush_failure_expect_batch_left_pending_without_retry_charge() -> (
    None
):
    """배치 flush가 실패하면 발행 완료로 표시하지 않고 retry count도 올리지 않는다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(2)
    ]

    storage = InMemoryAsyncOutboxStorage(pending=messages)
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(
        storage, FailingFlushAsyncTransport(), config
    )
    await relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []


@pytest.mark.asyncio
async def test_async_relay_batch_transport_stopped_expect_batch_left_pending_without_retry_charge() -> (
    None
):
    """종료로 transport가 닫히면 배치를 그대로 두고 retry count를 올리지 않는다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(3)
    ]

    storage = InMemoryAsyncOutboxStorage(pending=messages)
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, StoppedAsyncTransport(), config)
    await relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []


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


def test_relay_run_polls_batch_then_exits_when_stop_set_during_batch() -> None:
    """run 루프가 최소 한 번 _relay_batch를 실행한 뒤 stop_event에 반응해 종료한다."""

    class StopOnFetchStorage(InMemorySyncOutboxStorage):
        def __init__(self, stop_event: threading.Event) -> None:
            super().__init__()
            self._stop_event = stop_event
            self.fetch_calls = 0

        def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
            self.fetch_calls += 1
            self._stop_event.set()
            return []

    stop_event = threading.Event()
    storage = StopOnFetchStorage(stop_event)
    transport = SpySyncTransport()
    config = _make_config()

    relay = OutboxRelayBackgroundService(storage, transport, config)
    relay.set_stop_event(stop_event)
    relay.run()

    assert storage.fetch_calls == 1


@pytest.mark.asyncio
async def test_async_relay_run_async_breaks_when_stop_event_set_during_batch() -> None:
    """run_async가 _relay_batch 도중 stop_event가 set되면 wait_for에서 break로 종료한다."""

    class StopOnFetchAsyncStorage(InMemoryAsyncOutboxStorage):
        def __init__(self, stop_event: asyncio.Event) -> None:
            super().__init__()
            self._stop_event = stop_event
            self.fetch_calls = 0

        async def fetch_pending(
            self, limit: int, max_retry: int
        ) -> list[OutboxMessage]:
            self.fetch_calls += 1
            self._stop_event.set()
            return []

    stop_event = asyncio.Event()
    storage = StopOnFetchAsyncStorage(stop_event)
    transport = SpyAsyncTransport()
    config = _make_config()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, config)
    relay.set_stop_event(stop_event)

    await relay.run_async()

    assert storage.fetch_calls == 1


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


# ── partition key propagation tests ──


def test_relay_batch_forwards_stored_partition_key_to_transport() -> None:
    """_relay_batch가 저장된 partition_key를 Transport에 그대로 전달하는지 검증한다."""
    message = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-100"),
        partition_key="ORD-100",
    )

    transport = SpySyncTransport()
    relay = OutboxRelayBackgroundService(
        InMemorySyncOutboxStorage(pending=[message]),
        transport,
        _make_config(),
    )
    relay._relay_batch()

    assert transport.partition_keys == ["ORD-100"]


def test_relay_batch_forwards_none_when_message_has_no_partition_key() -> None:
    """partition_key가 없는 메시지는 Transport에 None으로 전달되는지 검증한다."""
    message = _make_message(RelayTestIntegrationEvent(order_id="ORD-101"))

    transport = SpySyncTransport()
    relay = OutboxRelayBackgroundService(
        InMemorySyncOutboxStorage(pending=[message]),
        transport,
        _make_config(),
    )
    relay._relay_batch()

    assert transport.partition_keys == [None]


@pytest.mark.asyncio
async def test_async_relay_batch_forwards_stored_partition_key_to_transport() -> None:
    """비동기 _relay_batch가 저장된 partition_key를 Transport에 전달하는지 검증한다."""
    message = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-200"),
        partition_key="ORD-200",
    )

    transport = SpyAsyncTransport()
    relay = AsyncOutboxRelayBackgroundService(
        InMemoryAsyncOutboxStorage(pending=[message]),
        transport,
        _make_config(),
    )
    await relay._relay_batch()

    assert transport.partition_keys == ["ORD-200"]


@pytest.mark.asyncio
async def test_async_relay_batch_forwards_none_when_message_has_no_partition_key() -> (
    None
):
    """비동기 경로에서 partition_key 없는 메시지가 None으로 전달되는지 검증한다."""
    message = _make_message(RelayTestIntegrationEvent(order_id="ORD-201"))

    transport = SpyAsyncTransport()
    relay = AsyncOutboxRelayBackgroundService(
        InMemoryAsyncOutboxStorage(pending=[message]),
        transport,
        _make_config(),
    )
    await relay._relay_batch()

    assert transport.partition_keys == [None]
