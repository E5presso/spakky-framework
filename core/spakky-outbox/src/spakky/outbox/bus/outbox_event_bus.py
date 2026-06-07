"""Outbox Event Bus — sync and async implementations replacing IEventBus/IAsyncEventBus via @Primary."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.event_publisher import IAsyncEventBus, IEventBus
from spakky.tracing.propagator import ITracePropagator
from typing import override

from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage


@Primary()
@Pod()
class OutboxEventBus(IEventBus):
    """Intercepts integration events and stores them in the Outbox table (sync).

    Replaces the default DirectEventBus so that events are persisted
    atomically within the same database transaction as the business data.
    """

    _storage: IOutboxStorage
    _propagator: ITracePropagator
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector

    def __init__(
        self,
        storage: IOutboxStorage,
        propagator: ITracePropagator,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        self._storage = storage
        self._propagator = propagator
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
        )
        self._storage.save(message)


@Primary()
@Pod()
class AsyncOutboxEventBus(IAsyncEventBus):
    """Intercepts integration events and stores them in the Outbox table (async).

    Replaces the default AsyncDirectEventBus so that events are persisted
    atomically within the same database transaction as the business data.
    """

    _storage: IAsyncOutboxStorage
    _propagator: ITracePropagator
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector

    def __init__(
        self,
        storage: IAsyncOutboxStorage,
        propagator: ITracePropagator,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        self._storage = storage
        self._propagator = propagator
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
        )
        await self._storage.save(message)
