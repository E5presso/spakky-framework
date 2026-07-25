"""Outbox Relay Background Services (sync and async)."""

import logging
from asyncio import wait_for
from uuid import UUID

from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.event.error import EventTransportNotRunningError
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport
from typing import override

from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage

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
        """Initialize with storage, transport, and config dependencies."""
        self._storage = storage
        self._transport = transport
        self._config = config

    @override
    def initialize(self) -> None:
        """No-op initialization for the relay service."""
        return

    @override
    def dispose(self) -> None:
        """No-op disposal for the relay service."""
        return

    @override
    def run(self) -> None:
        """Poll the outbox storage and relay pending messages until stopped."""
        while not self._stop_event.is_set():
            self._relay_batch()
            self._stop_event.wait(timeout=self._config.polling_interval_seconds)

    def _relay_batch(self) -> None:
        messages = self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        relayed_message_ids: list[UUID] = []
        # Keys whose earlier message the transport refused. Handing a later
        # message of the same key to the producer would put it ahead of the
        # refused one on the same broker partition, so the rest of the key waits
        # for a later poll. Messages without a partition key carry no ordering
        # claim and keep skipping past failures as before.
        halted_partition_keys: set[str] = set()
        for message in messages:
            if message.partition_key in halted_partition_keys:
                continue
            try:
                self._transport.send(
                    message.event_name,
                    message.payload,
                    message.headers,
                    message.partition_key,
                )
            except EventTransportNotRunningError:
                # Application shutdown closed the transport. The batch is left
                # untouched: a shutdown is nobody's delivery failure, and
                # charging retries here would exhaust healthy messages.
                logger.info(
                    "Transport stopped while relaying; deferring %d outbox messages",
                    len(messages) - len(relayed_message_ids),
                )
                return
            except Exception:
                logger.exception(
                    "Failed to relay outbox message %s",
                    message.id,
                )
                if message.retry_count + 1 >= self._config.max_retry_count:
                    # The retry budget is spent, so this message will never be
                    # fetched again. Abandoning it explicitly keeps its
                    # partition key from waiting on a message nobody will retry,
                    # and leaves the record findable instead of silently stuck.
                    self._storage.mark_abandoned(message.id)
                    continue
                self._storage.increment_retry(message.id)
                if message.partition_key is not None:
                    halted_partition_keys.add(message.partition_key)
                continue
            relayed_message_ids.append(message.id)
        if not relayed_message_ids:
            return
        # The batch is marked published only after flush() returns, so a batch
        # that never left the client stays pending. Retry counts are not charged
        # here: a flush failure belongs to the transport, not to any one message.
        try:
            self._transport.flush()
        except Exception:
            logger.exception(
                "Failed to flush %d relayed outbox messages",
                len(relayed_message_ids),
            )
            return
        for message_id in relayed_message_ids:
            self._storage.mark_published(message_id)


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
        """Initialize with async storage, transport, and config dependencies."""
        self._storage = storage
        self._transport = transport
        self._config = config

    @override
    async def initialize_async(self) -> None:
        """No-op async initialization for the relay service."""
        return

    @override
    async def dispose_async(self) -> None:
        """No-op async disposal for the relay service."""
        return

    @override
    async def run_async(self) -> None:
        """Poll the outbox storage and relay pending messages asynchronously."""
        while not self._stop_event.is_set():
            await self._relay_batch()
            try:
                await wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.polling_interval_seconds,
                )
                break
            except TimeoutError:
                continue

    async def _relay_batch(self) -> None:
        messages = await self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        relayed_message_ids: list[UUID] = []
        # Keys whose earlier message the transport refused. Handing a later
        # message of the same key to the producer would put it ahead of the
        # refused one on the same broker partition, so the rest of the key waits
        # for a later poll. Messages without a partition key carry no ordering
        # claim and keep skipping past failures as before.
        halted_partition_keys: set[str] = set()
        for message in messages:
            if message.partition_key in halted_partition_keys:
                continue
            try:
                await self._transport.send(
                    message.event_name,
                    message.payload,
                    message.headers,
                    message.partition_key,
                )
            except EventTransportNotRunningError:
                # Application shutdown closed the transport. The batch is left
                # untouched: a shutdown is nobody's delivery failure, and
                # charging retries here would exhaust healthy messages.
                logger.info(
                    "Transport stopped while relaying; deferring %d outbox messages",
                    len(messages) - len(relayed_message_ids),
                )
                return
            except Exception:
                logger.exception(
                    "Failed to relay outbox message %s",
                    message.id,
                )
                if message.retry_count + 1 >= self._config.max_retry_count:
                    # The retry budget is spent, so this message will never be
                    # fetched again. Abandoning it explicitly keeps its
                    # partition key from waiting on a message nobody will retry,
                    # and leaves the record findable instead of silently stuck.
                    await self._storage.mark_abandoned(message.id)
                    continue
                await self._storage.increment_retry(message.id)
                if message.partition_key is not None:
                    halted_partition_keys.add(message.partition_key)
                continue
            relayed_message_ids.append(message.id)
        if not relayed_message_ids:
            return
        # The batch is marked published only after flush() returns, so a batch
        # that never left the client stays pending. Retry counts are not charged
        # here: a flush failure belongs to the transport, not to any one message.
        try:
            await self._transport.flush()
        except Exception:
            logger.exception(
                "Failed to flush %d relayed outbox messages",
                len(relayed_message_ids),
            )
            return
        for message_id in relayed_message_ids:
            await self._storage.mark_published(message_id)
