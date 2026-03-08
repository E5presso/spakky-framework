from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventBus

from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.session_manager import AsyncSessionManager


@Primary()
@Pod()
class AsyncOutboxEventBus(IAsyncEventBus):
    """IAsyncEventBus implementation that stores integration events in the Outbox table.

    Decorated with ``@Primary`` so that when ``spakky-outbox`` is loaded alongside
    ``spakky-event``, this bus takes precedence over ``AsyncDirectEventBus``.

    Because this bus is invoked inside the TransactionalEventPublishingAspect (which
    runs inside the TransactionalAspect), the session is already open and the write
    is part of the same database transaction as the business data — guaranteeing
    atomicity.

    The OutboxRelay background service later polls the table and forwards pending
    messages to the original IAsyncEventTransport.
    """

    _session_manager: AsyncSessionManager

    def __init__(self, session_manager: AsyncSessionManager) -> None:
        self._session_manager = session_manager

    async def send(self, event: AbstractIntegrationEvent) -> None:
        """Persist an integration event to the outbox table.

        Args:
            event: The integration event to store.
        """
        event_type = type(event)
        fqcn = f"{event_type.__module__}.{event_type.__qualname__}"
        adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(event_type)
        message = OutboxMessageTable(
            event_name=event.event_name,
            event_type=fqcn,
            payload=adapter.dump_json(event),
        )
        self._session_manager.session.add(message)
        await self._session_manager.session.flush()
