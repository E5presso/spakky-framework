"""Outbox Relay Background Services (sync and async)."""

import logging
from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import wait_for

from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage

logger = logging.getLogger(__name__)


@Pod()
class OutboxRelayBackgroundService(AbstractBackgroundService):
    """Polls the Outbox storage and relays pending messages to the transport (sync)."""

    _storage: IOutboxStorage
    _transport: IEventTransport
    _config: OutboxConfig

    def __init__(
        self,
        storage: IOutboxStorage,
        transport: IEventTransport,
        config: OutboxConfig,
    ) -> None:
        self._storage = storage
        self._transport = transport
        self._config = config

    def initialize(self) -> None:
        return

    def dispose(self) -> None:
        return

    def run(self) -> None:
        while not self._stop_event.is_set():
            self._relay_batch()
            self._stop_event.wait(timeout=self._config.polling_interval_seconds)

    def _relay_batch(self) -> None:
        messages = self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        for message in messages:
            try:
                self._transport.send(message.event_name, message.payload)
                self._storage.mark_published(message.id)
            except Exception:
                logger.exception(
                    "Failed to relay outbox message %s",
                    message.id,
                )
                self._storage.increment_retry(message.id)


@Pod()
class AsyncOutboxRelayBackgroundService(AbstractAsyncBackgroundService):
    """Polls the Outbox storage and relays pending messages to the transport (async)."""

    _storage: IAsyncOutboxStorage
    _transport: IAsyncEventTransport
    _config: OutboxConfig

    def __init__(
        self,
        storage: IAsyncOutboxStorage,
        transport: IAsyncEventTransport,
        config: OutboxConfig,
    ) -> None:
        self._storage = storage
        self._transport = transport
        self._config = config

    async def initialize_async(self) -> None:
        return

    async def dispose_async(self) -> None:
        return

    async def run_async(self) -> None:
        while not self._stop_event.is_set():
            await self._relay_batch()
            try:
                await wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.polling_interval_seconds,
                )
                break  # pragma: no cover - graceful shutdown path, timing-sensitive
            except AsyncTimeoutError:
                continue

    async def _relay_batch(self) -> None:
        messages = await self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        for message in messages:
            try:
                await self._transport.send(message.event_name, message.payload)
                await self._storage.mark_published(message.id)
            except Exception:
                logger.exception(
                    "Failed to relay outbox message %s",
                    message.id,
                )
                await self._storage.increment_retry(message.id)
