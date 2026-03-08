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

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.session_manager import AsyncSessionManager

logger = getLogger(__name__)


@Pod()
class OutboxRelay(AbstractAsyncBackgroundService):
    """Background service that polls the outbox table and forwards pending messages.

    Uses an independent session lifecycle (open/commit/close per batch) so that the
    relay's database operations are completely separate from request-scoped business
    transactions.

    Delivery guarantees:
    - At-least-once: messages are retried up to ``max_retry_count`` times.
    - ``WITH FOR UPDATE SKIP LOCKED`` prevents duplicate processing in multi-instance
      deployments.

    Note:
        The ``spakky_event_outbox`` table must be created by the application's
        database migration tooling (e.g. Alembic) before the relay starts polling.
    """

    _session_manager: AsyncSessionManager
    _transport: IAsyncEventTransport
    _config: OutboxConfig

    def __init__(
        self,
        session_manager: AsyncSessionManager,
        transport: IAsyncEventTransport,
        config: OutboxConfig,
    ) -> None:
        self._session_manager = session_manager
        self._transport = transport
        self._config = config

    async def initialize_async(self) -> None:
        """No-op: the outbox table is managed by database migrations."""

    async def dispose_async(self) -> None:
        """No-op: session lifecycle is managed per batch in _relay_batch."""

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
        await self._session_manager.open()
        try:
            result = await self._session_manager.session.execute(
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
                    module_path, _, class_name = message.event_type.rpartition(".")
                    module = importlib.import_module(module_path)
                    event_class = cast(
                        type[AbstractIntegrationEvent], getattr(module, class_name)
                    )
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

            await self._session_manager.session.commit()
        finally:
            await self._session_manager.close()
