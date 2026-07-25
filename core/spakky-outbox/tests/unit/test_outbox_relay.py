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
from spakky.event.error import (
    EventDeliveryRejectedError,
    EventTransportNotRunningError,
)
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


class SelectivelyFailingSyncTransport(IEventTransport):
    """Rejects the given payloads and records every payload it accepts."""

    def __init__(self, rejected_payloads: set[bytes]) -> None:
        self.rejected_payloads = rejected_payloads
        self.sent_payloads: list[bytes] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        if payload in self.rejected_payloads:
            raise ConnectionError("Transport rejected the message")
        self.sent_payloads.append(payload)

    def flush(self) -> None:
        return


class RefusingOnFlushSyncTransport(IEventTransport):
    """Accepts every send and reports the broker's refusal at flush, like Kafka."""

    def __init__(self, refused_payloads: set[bytes]) -> None:
        self.refused_payloads = refused_payloads
        self.pending_payloads: list[bytes] = []
        self.sent_payloads: list[bytes] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.pending_payloads.append(payload)

    def flush(self) -> None:
        pending = self.pending_payloads
        self.pending_payloads = []
        refused = [p for p in pending if p in self.refused_payloads]
        if refused:
            raise EventDeliveryRejectedError(["MSG_SIZE_TOO_LARGE"] * len(refused))
        self.sent_payloads.extend(pending)


class StoppingDuringReplaySyncTransport(IEventTransport):
    """Fails the batch flush, then reports shutdown when the replay resends."""

    def __init__(self) -> None:
        self.flush_attempts = 0

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        if self.flush_attempts > 0:
            raise EventTransportNotRunningError

    def flush(self) -> None:
        self.flush_attempts += 1
        raise ConnectionError("Broker unreachable")


class InMemorySyncOutboxStorage(IOutboxStorage):
    def __init__(self, pending: list[OutboxMessage] | None = None) -> None:
        self.pending: list[OutboxMessage] = pending or []
        self.published_ids: list[object] = []
        self.retried_ids: list[object] = []
        self.abandoned_ids: list[object] = []

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

    def mark_abandoned(self, message_id: object) -> None:
        self.abandoned_ids.append(message_id)


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


class SelectivelyFailingAsyncTransport(IAsyncEventTransport):
    """Rejects the given payloads and records every payload it accepts."""

    def __init__(self, rejected_payloads: set[bytes]) -> None:
        self.rejected_payloads = rejected_payloads
        self.sent_payloads: list[bytes] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        if payload in self.rejected_payloads:
            raise ConnectionError("Transport rejected the message")
        self.sent_payloads.append(payload)

    async def flush(self) -> None:
        return


class RefusingOnFlushAsyncTransport(IAsyncEventTransport):
    """Accepts every send and reports the broker's refusal at flush, like Kafka."""

    def __init__(self, refused_payloads: set[bytes]) -> None:
        self.refused_payloads = refused_payloads
        self.pending_payloads: list[bytes] = []
        self.sent_payloads: list[bytes] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.pending_payloads.append(payload)

    async def flush(self) -> None:
        pending = self.pending_payloads
        self.pending_payloads = []
        refused = [p for p in pending if p in self.refused_payloads]
        if refused:
            raise EventDeliveryRejectedError(["MSG_SIZE_TOO_LARGE"] * len(refused))
        self.sent_payloads.extend(pending)


class StoppingDuringReplayAsyncTransport(IAsyncEventTransport):
    """Fails the batch flush, then reports shutdown when the replay resends."""

    def __init__(self) -> None:
        self.flush_attempts = 0

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        if self.flush_attempts > 0:
            raise EventTransportNotRunningError

    async def flush(self) -> None:
        self.flush_attempts += 1
        raise ConnectionError("Broker unreachable")


class InMemoryAsyncOutboxStorage(IAsyncOutboxStorage):
    def __init__(self, pending: list[OutboxMessage] | None = None) -> None:
        self.pending: list[OutboxMessage] = pending or []
        self.published_ids: list[object] = []
        self.retried_ids: list[object] = []
        self.abandoned_ids: list[object] = []

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

    async def mark_abandoned(self, message_id: object) -> None:
        self.abandoned_ids.append(message_id)


# ── Common helpers ──


def _make_message(
    event: AbstractIntegrationEvent,
    partition_key: str | None = None,
    retry_count: int = 0,
) -> OutboxMessage:
    adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
    return OutboxMessage(
        id=uuid4(),
        event_name=event.event_name,
        payload=adapter.dump_json(event),
        headers={"traceparent": "00-abc123-def456-01"},
        partition_key=partition_key,
        created_at=datetime.now(UTC),
        retry_count=retry_count,
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


def test_relay_batch_broker_unreachable_expect_batch_left_pending_without_retry() -> (
    None
):
    """브로커에 닿지 못하면 재확인이 멈추고 어느 메시지도 retry를 쓰지 않는다."""
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
    assert storage.abandoned_ids == []


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


def test_relay_batch_partition_key_after_failure_expect_rest_of_key_held_back() -> None:
    """같은 파티션 키의 선행 메시지가 실패하면 후속 메시지를 보류하는지 검증한다."""
    first = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    second = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemorySyncOutboxStorage(pending=[first, second])
    transport = SelectivelyFailingSyncTransport({first.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert transport.sent_payloads == []
    assert storage.published_ids == []
    assert storage.retried_ids == [first.id]


def test_relay_batch_partition_key_failure_expect_other_keys_unaffected() -> None:
    """한 파티션 키의 실패가 다른 키의 발행을 막지 않는지 검증한다."""
    failing = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    other_key = _make_message(
        RelayTestIntegrationEvent(order_id="CART-1"), partition_key="CART"
    )

    storage = InMemorySyncOutboxStorage(pending=[failing, other_key])
    transport = SelectivelyFailingSyncTransport({failing.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert transport.sent_payloads == [other_key.payload]
    assert storage.published_ids == [other_key.id]


def test_relay_batch_without_partition_key_expect_failure_skipped() -> None:
    """파티션 키가 없는 메시지는 실패를 건너뛰고 계속 발행되는지 검증한다."""
    failing = _make_message(RelayTestIntegrationEvent(order_id="ORD-1"))
    following = _make_message(RelayTestIntegrationEvent(order_id="ORD-2"))

    storage = InMemorySyncOutboxStorage(pending=[failing, following])
    transport = SelectivelyFailingSyncTransport({failing.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]
    assert storage.retried_ids == [failing.id]


def test_relay_batch_retry_budget_spent_expect_message_abandoned() -> None:
    """마지막 재시도까지 실패한 메시지를 발행 포기 처리하는지 검증한다."""
    message = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )

    storage = InMemorySyncOutboxStorage(pending=[message])
    transport = SelectivelyFailingSyncTransport({message.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert storage.abandoned_ids == [message.id]
    assert storage.retried_ids == []
    assert storage.published_ids == []


def test_relay_batch_abandoned_message_expect_partition_key_released() -> None:
    """발행 포기한 메시지가 같은 키의 후속 메시지를 막지 않는지 검증한다."""
    exhausted = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )
    following = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemorySyncOutboxStorage(pending=[exhausted, following])
    transport = SelectivelyFailingSyncTransport({exhausted.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert storage.abandoned_ids == [exhausted.id]
    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]


def test_relay_batch_flush_refusal_expect_rest_of_key_held_back() -> None:
    """flush에서 거부된 메시지가 같은 키의 후속 메시지를 보류시키는지 검증한다."""
    first = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    second = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemorySyncOutboxStorage(pending=[first, second])
    transport = RefusingOnFlushSyncTransport({first.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert transport.sent_payloads == []
    assert storage.published_ids == []
    assert storage.retried_ids == [first.id]


def test_relay_batch_flush_refusal_expect_other_keys_published() -> None:
    """flush 거부가 다른 파티션 키의 발행을 막지 않는지 검증한다."""
    refused = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    other_key = _make_message(
        RelayTestIntegrationEvent(order_id="CART-1"), partition_key="CART"
    )

    storage = InMemorySyncOutboxStorage(pending=[refused, other_key])
    transport = RefusingOnFlushSyncTransport({refused.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert transport.sent_payloads == [other_key.payload]
    assert storage.published_ids == [other_key.id]
    assert storage.retried_ids == [refused.id]


def test_relay_batch_flush_refusal_with_budget_spent_expect_abandoned() -> None:
    """flush 거부로 재시도를 소진한 메시지를 발행 포기하고 키를 여는지 검증한다."""
    exhausted = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )
    following = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemorySyncOutboxStorage(pending=[exhausted, following])
    transport = RefusingOnFlushSyncTransport({exhausted.payload})

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert storage.abandoned_ids == [exhausted.id]
    assert storage.retried_ids == []
    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]


def test_relay_batch_shutdown_during_replay_expect_batch_left_pending() -> None:
    """flush 실패 후 재확인 중 transport가 닫히면 남은 배치를 그대로 두는지 검증한다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(2)
    ]

    storage = InMemorySyncOutboxStorage(pending=messages)
    transport = StoppingDuringReplaySyncTransport()

    relay = OutboxRelayBackgroundService(storage, transport, _make_config())
    relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []
    assert storage.abandoned_ids == []


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
async def test_async_relay_batch_broker_unreachable_expect_no_retry_charged() -> None:
    """브로커에 닿지 못하면 재확인이 멈추고 어느 메시지도 retry를 쓰지 않는다."""
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
    assert storage.abandoned_ids == []


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
async def test_async_relay_batch_partition_key_after_failure_expect_key_held_back() -> (
    None
):
    """같은 파티션 키의 선행 메시지가 실패하면 후속 메시지를 보류하는지 검증한다."""
    first = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    second = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[first, second])
    transport = SelectivelyFailingAsyncTransport({first.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert transport.sent_payloads == []
    assert storage.published_ids == []
    assert storage.retried_ids == [first.id]


@pytest.mark.asyncio
async def test_async_relay_batch_partition_key_failure_expect_other_keys_unaffected() -> (
    None
):
    """한 파티션 키의 실패가 다른 키의 발행을 막지 않는지 검증한다."""
    failing = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    other_key = _make_message(
        RelayTestIntegrationEvent(order_id="CART-1"), partition_key="CART"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[failing, other_key])
    transport = SelectivelyFailingAsyncTransport({failing.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert transport.sent_payloads == [other_key.payload]
    assert storage.published_ids == [other_key.id]


@pytest.mark.asyncio
async def test_async_relay_batch_without_partition_key_expect_failure_skipped() -> None:
    """파티션 키가 없는 메시지는 실패를 건너뛰고 계속 발행되는지 검증한다."""
    failing = _make_message(RelayTestIntegrationEvent(order_id="ORD-1"))
    following = _make_message(RelayTestIntegrationEvent(order_id="ORD-2"))

    storage = InMemoryAsyncOutboxStorage(pending=[failing, following])
    transport = SelectivelyFailingAsyncTransport({failing.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]
    assert storage.retried_ids == [failing.id]


@pytest.mark.asyncio
async def test_async_relay_batch_retry_budget_spent_expect_message_abandoned() -> None:
    """마지막 재시도까지 실패한 메시지를 발행 포기 처리하는지 검증한다."""
    message = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )

    storage = InMemoryAsyncOutboxStorage(pending=[message])
    transport = SelectivelyFailingAsyncTransport({message.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert storage.abandoned_ids == [message.id]
    assert storage.retried_ids == []
    assert storage.published_ids == []


@pytest.mark.asyncio
async def test_async_relay_batch_abandoned_expect_partition_key_released() -> None:
    """발행 포기한 메시지가 같은 키의 후속 메시지를 막지 않는지 검증한다."""
    exhausted = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )
    following = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[exhausted, following])
    transport = SelectivelyFailingAsyncTransport({exhausted.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert storage.abandoned_ids == [exhausted.id]
    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]


@pytest.mark.asyncio
async def test_async_relay_batch_flush_refusal_expect_rest_of_key_held_back() -> None:
    """flush에서 거부된 메시지가 같은 키의 후속 메시지를 보류시키는지 검증한다."""
    first = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    second = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[first, second])
    transport = RefusingOnFlushAsyncTransport({first.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert transport.sent_payloads == []
    assert storage.published_ids == []
    assert storage.retried_ids == [first.id]


@pytest.mark.asyncio
async def test_async_relay_batch_flush_refusal_expect_other_keys_published() -> None:
    """flush 거부가 다른 파티션 키의 발행을 막지 않는지 검증한다."""
    refused = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"), partition_key="ORD"
    )
    other_key = _make_message(
        RelayTestIntegrationEvent(order_id="CART-1"), partition_key="CART"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[refused, other_key])
    transport = RefusingOnFlushAsyncTransport({refused.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert transport.sent_payloads == [other_key.payload]
    assert storage.published_ids == [other_key.id]
    assert storage.retried_ids == [refused.id]


@pytest.mark.asyncio
async def test_async_relay_batch_flush_refusal_budget_spent_expect_abandoned() -> None:
    """flush 거부로 재시도를 소진한 메시지를 발행 포기하고 키를 여는지 검증한다."""
    exhausted = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-1"),
        partition_key="ORD",
        retry_count=2,
    )
    following = _make_message(
        RelayTestIntegrationEvent(order_id="ORD-2"), partition_key="ORD"
    )

    storage = InMemoryAsyncOutboxStorage(pending=[exhausted, following])
    transport = RefusingOnFlushAsyncTransport({exhausted.payload})

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert storage.abandoned_ids == [exhausted.id]
    assert storage.retried_ids == []
    assert transport.sent_payloads == [following.payload]
    assert storage.published_ids == [following.id]


@pytest.mark.asyncio
async def test_async_relay_batch_shutdown_during_replay_expect_batch_left_pending() -> (
    None
):
    """flush 실패 후 재확인 중 transport가 닫히면 남은 배치를 그대로 두는지 검증한다."""
    messages = [
        _make_message(RelayTestIntegrationEvent(order_id=f"ORD-{index}"))
        for index in range(2)
    ]

    storage = InMemoryAsyncOutboxStorage(pending=messages)
    transport = StoppingDuringReplayAsyncTransport()

    relay = AsyncOutboxRelayBackgroundService(storage, transport, _make_config())
    await relay._relay_batch()

    assert storage.published_ids == []
    assert storage.retried_ids == []
    assert storage.abandoned_ids == []


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
