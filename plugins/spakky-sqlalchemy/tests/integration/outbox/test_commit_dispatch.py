"""@Transactional commit 직후 outbox relay가 polling을 기다리지 않고 보내는지 PostgreSQL로 검증한다."""

import asyncio
import threading

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.common.mutability import immutable
from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport
from spakky.outbox.bus.outbox_event_bus import AsyncOutboxEventBus, OutboxEventBus
from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.relay.relay import (
    AsyncOutboxRelayBackgroundService,
    OutboxRelayBackgroundService,
)
from spakky.outbox.relay.wakeup import OutboxRelayWakeup
from spakky.tracing import W3CTracePropagator

from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)

SIGNAL_TIMEOUT_SECONDS = 10.0
"""Upper bound for waiting on the relay; never reached when the test passes."""

LONG_POLLING_INTERVAL_SECONDS = 3600.0
"""Polling interval long enough that only the commit wake-up can send the message."""


@immutable
class OrderPlacedIntegrationEvent(AbstractIntegrationEvent):
    order_id: str


class FirstReadSignalingStorage(SqlAlchemyOutboxStorage):
    """Real storage that signals once the relay finished its startup read."""

    def __init__(self, app: SpakkyApplication, config: OutboxConfig) -> None:
        super().__init__(
            app.container.get(type_=SessionManager),
            app.container.get(type_=ConnectionManager),
            config,
        )
        self.first_read_done = threading.Event()

    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        messages = super().fetch_pending(limit, max_retry)
        self.first_read_done.set()
        return messages


class AsyncFirstReadSignalingStorage(AsyncSqlAlchemyOutboxStorage):
    """Real async storage that signals once the relay finished its startup read."""

    def __init__(self, app: SpakkyApplication, config: OutboxConfig) -> None:
        super().__init__(
            app.container.get(type_=AsyncSessionManager),
            app.container.get(type_=AsyncConnectionManager),
            config,
        )
        self.first_read_done = asyncio.Event()

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        messages = await super().fetch_pending(limit, max_retry)
        self.first_read_done.set()
        return messages


class WaitingTransport(IEventTransport):
    """Signals when a payload containing the expected marker was flushed."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.encode()
        self.pending: list[bytes] = []
        self.delivered = threading.Event()

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.pending.append(payload)

    def flush(self) -> None:
        if any(self.marker in payload for payload in self.pending):
            self.delivered.set()
        self.pending = []


class AsyncWaitingTransport(IAsyncEventTransport):
    """Signals when a payload containing the expected marker was flushed."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.encode()
        self.pending: list[bytes] = []
        self.delivered = asyncio.Event()

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        self.pending.append(payload)

    async def flush(self) -> None:
        if any(self.marker in payload for payload in self.pending):
            self.delivered.set()
        self.pending = []


def _long_polling_config() -> OutboxConfig:
    config = OutboxConfig()
    config.polling_interval_seconds = LONG_POLLING_INTERVAL_SECONDS
    return config


@pytest.mark.integration
def test_commit_expect_relay_sends_message_without_waiting_for_poll(
    app: SpakkyApplication,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """@Transactional이 commit하면 polling 주기 전에 그 transaction의 메시지가 나간다."""
    config = _long_polling_config()
    storage = FirstReadSignalingStorage(app, config)
    synchronization = TransactionSynchronization()
    wakeup = OutboxRelayWakeup()
    transport = WaitingTransport(unique_id)
    relay = OutboxRelayBackgroundService(storage, transport, config, wakeup)
    bus = OutboxEventBus(storage, W3CTracePropagator(), synchronization, wakeup)
    aspect = TransactionalAspect(transaction, AggregateCollector(), synchronization)

    @Transactional()
    def place_order() -> None:
        bus.send(OrderPlacedIntegrationEvent(order_id=unique_id))

    relay.set_stop_event(threading.Event())
    relay.start()
    try:
        assert storage.first_read_done.wait(SIGNAL_TIMEOUT_SECONDS)

        aspect.around(place_order)

        assert transport.delivered.wait(SIGNAL_TIMEOUT_SECONDS)
    finally:
        relay.stop()


@pytest.mark.integration
async def test_async_commit_expect_relay_sends_message_without_waiting_for_poll(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """비동기 @Transactional commit 뒤에도 polling 주기 전에 메시지가 나간다."""
    config = _long_polling_config()
    storage = AsyncFirstReadSignalingStorage(app, config)
    synchronization = TransactionSynchronization()
    wakeup = OutboxRelayWakeup()
    transport = AsyncWaitingTransport(unique_id)
    relay = AsyncOutboxRelayBackgroundService(storage, transport, config, wakeup)
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator(), synchronization, wakeup)
    aspect = AsyncTransactionalAspect(
        async_transaction, AggregateCollector(), synchronization
    )

    @Transactional()
    async def place_order() -> None:
        await bus.send(OrderPlacedIntegrationEvent(order_id=unique_id))

    relay.set_stop_event(asyncio.Event())
    await relay.start_async()
    try:
        await asyncio.wait_for(storage.first_read_done.wait(), SIGNAL_TIMEOUT_SECONDS)

        await aspect.around_async(place_order)

        await asyncio.wait_for(transport.delivered.wait(), SIGNAL_TIMEOUT_SECONDS)
    finally:
        await relay.stop_async()
