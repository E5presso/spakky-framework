"""Default EventBus implementations that delegate to EventTransport."""

from typing import override

from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing.propagator import ITracePropagator

from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventTransport,
    IEventBus,
    IEventTransport,
)


@Pod()
class DirectEventBus(IEventBus):
    """Synchronous event bus that serializes and delegates to IEventTransport."""

    _transport: IEventTransport
    _propagator: ITracePropagator
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector
    _adapters: dict[type, TypeAdapter[AbstractIntegrationEvent]]

    def __init__(
        self,
        transport: IEventTransport,
        propagator: ITracePropagator,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        """Initialize with the given transport and trace propagator."""
        self._transport = transport
        self._propagator = propagator
        self._auth_snapshot_headers = (
            auth_snapshot_headers or AuthContextSnapshotHeaderInjector()
        )
        self._adapters = {}

    @override
    def send(self, event: AbstractIntegrationEvent) -> None:
        """Serialize and send an integration event via transport."""
        event_type = type(event)
        if event_type not in self._adapters:
            self._adapters[event_type] = TypeAdapter(event_type)
        adapter = self._adapters[event_type]
        headers: dict[str, str] = {}
        self._propagator.inject(headers)
        self._auth_snapshot_headers.inject(headers)
        self._transport.send(
            event.event_name,
            adapter.dump_json(event),
            headers,
        )


@Pod()
class AsyncDirectEventBus(IAsyncEventBus):
    """Asynchronous event bus that serializes and delegates to IAsyncEventTransport."""

    _transport: IAsyncEventTransport
    _propagator: ITracePropagator
    _auth_snapshot_headers: AuthContextSnapshotHeaderInjector
    _adapters: dict[type, TypeAdapter[AbstractIntegrationEvent]]

    def __init__(
        self,
        transport: IAsyncEventTransport,
        propagator: ITracePropagator,
        auth_snapshot_headers: AuthContextSnapshotHeaderInjector | None = None,
    ) -> None:
        """Initialize with the given async transport and trace propagator."""
        self._transport = transport
        self._propagator = propagator
        self._auth_snapshot_headers = (
            auth_snapshot_headers or AuthContextSnapshotHeaderInjector()
        )
        self._adapters = {}

    @override
    async def send(self, event: AbstractIntegrationEvent) -> None:
        """Serialize and send an integration event via async transport."""
        event_type = type(event)
        if event_type not in self._adapters:
            self._adapters[event_type] = TypeAdapter(event_type)
        adapter = self._adapters[event_type]
        headers: dict[str, str] = {}
        self._propagator.inject(headers)
        self._auth_snapshot_headers.inject(headers)
        await self._transport.send(
            event.event_name,
            adapter.dump_json(event),
            headers,
        )
