import importlib
from asyncio import TimeoutError, wait_for
from datetime import UTC, datetime
from logging import getLogger
from typing import cast

from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import AbstractAsyncBackgroundService
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventTransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)

logger = getLogger(__name__)


def _import_string(dotted_path: str) -> type[AbstractIntegrationEvent]:
    """Import and return a class from its fully-qualified class name.

    Args:
        dotted_path: FQCN, e.g. ``my_app.events.OrderConfirmedIntegrationEvent``.

    Returns:
        The resolved class.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the class does not exist in the module.
    """
    module_path, _, class_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return cast(type[AbstractIntegrationEvent], getattr(module, class_name))


@Pod()
class OutboxRelay(AbstractAsyncBackgroundService):
    """Background service that polls the outbox table and forwards pending messages.

    Uses an independent SQLAlchemy session (not the CONTEXT-scoped session used by
    the business transaction) to avoid interfering with active requests.

    Delivery guarantees:
    - At-least-once: messages are retried up to ``max_retry_count`` times.
    - ``WITH FOR UPDATE SKIP LOCKED`` prevents duplicate processing in multi-instance
      deployments.
    """

    _engine: AsyncEngine
    _transport: IAsyncEventTransport
    _config: OutboxConfig

    def __init__(
        self,
        connection_manager: AsyncConnectionManager,
        transport: IAsyncEventTransport,
        config: OutboxConfig,
    ) -> None:
        self._engine = connection_manager.connection
        self._transport = transport
        self._config = config

    async def initialize_async(self) -> None:
        """Create the outbox table if auto_create_table is enabled."""
        if self._config.auto_create_table:
            async with self._engine.begin() as conn:
                await conn.run_sync(OutboxMessageTable.metadata.create_all)

    async def dispose_async(self) -> None:
        """No-op: engine lifecycle is managed by AsyncConnectionManager."""

    async def run_async(self) -> None:
        """Main polling loop. Runs until the stop event is set."""
        while not self._stop_event.is_set():
            await self._relay_batch()
            try:
                await wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.polling_interval_seconds,
                )
                break  # stop_event was set — exit cleanly
            except TimeoutError:
                continue  # normal timeout — poll again

    async def _relay_batch(self) -> None:
        """Fetch and deliver a batch of pending outbox messages."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                select(OutboxMessageTable)
                .where(OutboxMessageTable.published_at.is_(None))
                .where(OutboxMessageTable.retry_count < self._config.max_retry_count)
                .order_by(OutboxMessageTable.created_at)
                .limit(self._config.batch_size)
                .with_for_update(skip_locked=True)
            )
            messages = result.scalars().all()

            for message in messages:
                try:
                    event_class = _import_string(message.event_type)
                    adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(
                        event_class
                    )
                    event = adapter.validate_json(message.payload)
                    await self._transport.send(event)
                    message.published_at = datetime.now(UTC)
                except Exception:
                    logger.exception(
                        "Failed to relay outbox message id=%s type=%s",
                        message.id,
                        message.event_type,
                    )
                    message.retry_count += 1

            await session.commit()
