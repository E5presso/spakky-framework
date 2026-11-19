"""Outbox Event Bus — sync and async implementations replacing IEventBus/IAsyncEventBus via @Primary."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.event_publisher import IAsyncEventBus, IEventBus
from spakky.tracing.propagator import ITracePropagator
from typing import override

from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage
from spakky.outbox.relay.wakeup import OutboxRelayWakeup


@Primary()
@Pod()
class OutboxEventBus(IEventBus):
    """Intercepts integration events and stores them in the Outbox table (sync).

    Replaces the default DirectEventBus so that events are persisted
    atomically within the same database transaction as the business data.
    """

    _storage: IOutboxStorage
    _propagator: ITracePropagator
    _synchronization: TransactionSynchronization
    _wakeup: OutboxRelayWakeup
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector

    def __init__(
        self,
        storage: IOutboxStorage,
        propagator: ITracePropagator,
        synchronization: TransactionSynchronization,
        wakeup: OutboxRelayWakeup,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        self._storage = storage
        self._propagator = propagator
        self._synchronization = synchronization
        self._wakeup = wakeup
        self._auth_snapshot_headers = (
            auth_snapshot_headers or AuthContextSnapshotHeaderInjector()
        )

    @override
    def send(self, event: AbstractIntegrationEvent) -> None:
        adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
        headers: dict[str, str] = {}
        self._propagator.inject(headers)
        self._auth_snapshot_headers.inject(headers)
        message = OutboxMessage(
            id=uuid4(),
            event_name=event.event_name,
            payload=adapter.dump_json(event),
            headers=headers,
            created_at=datetime.now(UTC),
            partition_key=event.partition_key,
        )
        self._storage.save(message)
        self.__wake_relay_after_commit()

    def __wake_relay_after_commit(self) -> None:
        """Have the relays send this message as soon as its transaction commits.

        Outside a `@Transactional` call there is no commit to wait for; the
        message is then sent by the relay's next poll.
        """
        if not self._synchronization.is_active:
            return
        self._synchronization.register_after_commit(self._wakeup.notify)


@Primary()
@Pod()
class AsyncOutboxEventBus(IAsyncEventBus):
    """Intercepts integration events and stores them in the Outbox table (async).

    Replaces the default AsyncDirectEventBus so that events are persisted
    atomically within the same database transaction as the business data.
    """

    _storage: IAsyncOutboxStorage
    _propagator: ITracePropagator
    _synchronization: TransactionSynchronization
    _wakeup: OutboxRelayWakeup
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector

    def __init__(
        self,
        storage: IAsyncOutboxStorage,
        propagator: ITracePropagator,
        synchronization: TransactionSynchronization,
        wakeup: OutboxRelayWakeup,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        self._storage = storage
        self._propagator = propagator
        self._synchronization = synchronization
        self._wakeup = wakeup
        self._auth_snapshot_headers = (
            auth_snapshot_headers or AuthContextSnapshotHeaderInjector()
        )

    @override
    async def send(self, event: AbstractIntegrationEvent) -> None:
        adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(type(event))
        headers: dict[str, str] = {}
        self._propagator.inject(headers)
        self._auth_snapshot_headers.inject(headers)
        message = OutboxMessage(
            id=uuid4(),
            event_name=event.event_name,
            payload=adapter.dump_json(event),
            headers=headers,
            created_at=datetime.now(UTC),
            partition_key=event.partition_key,
        )
        await self._storage.save(message)
        self.__wake_relay_after_commit()

    def __wake_relay_after_commit(self) -> None:
        """Have the relays send this message as soon as its transaction commits.

        Outside a `@Transactional` call there is no commit to wait for; the
        message is then sent by the relay's next poll.
        """
        if not self._synchronization.is_active:
            return
        self._synchronization.register_after_commit(self._wakeup.notify)
