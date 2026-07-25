"""Outbox Relay Background Services (sync and async)."""

import logging
from asyncio import wait_for

from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.event.error import (
    EventDeliveryRejectedError,
    EventTransportNotRunningError,
)
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport
from typing import override

from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage
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

    def __register_refusal(
        self,
        message: OutboxMessage,
        halted_partition_keys: set[str],
    ) -> None:
        """Spend one retry on a refused message, or abandon it when none is left.

        A message whose budget is spent will never be fetched again, so it is
        abandoned rather than left behind: that releases its partition key,
        which would otherwise wait forever on a message nobody will retry, and
        keeps the record findable. A message that still has budget holds its key
        back until it is delivered, so nothing of that key overtakes it.
        """
        if message.retry_count + 1 >= self._config.max_retry_count:
            self._storage.mark_abandoned(message.id)
            return
        self._storage.increment_retry(message.id)
        if message.partition_key is not None:
            halted_partition_keys.add(message.partition_key)

    def __publish_one_at_a_time(
        self,
        messages: list[OutboxMessage],
        halted_partition_keys: set[str],
    ) -> None:
        """Replay a batch whose flush failed, confirming one message at a time.

        A batch flush reports that the broker refused something but not what, so
        neither the retry budget nor the partition key hold-back can be aimed
        without replaying. Confirming one message per flush puts the broker's
        verdict on the message that earned it: the refused message spends its
        budget and holds back the rest of its key, while its neighbours publish.
        Only a refusal counts — a transport that cannot reach the broker at all
        stops the replay untouched, because an outage is no message's fault.
        The replay can re-deliver a record the failed flush had already accepted
        — delivery stays at-least-once, which consumers already assume.
        """
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
                self._transport.flush()
            except EventDeliveryRejectedError:
                logger.exception("Broker refused outbox message %s", message.id)
                self.__register_refusal(message, halted_partition_keys)
                continue
            except Exception:
                # The transport itself is failing — a closed client, a lost
                # connection, a timeout. That is no single message's fault, so
                # the rest of the batch is left pending instead of spending
                # budgets that would abandon healthy messages during an outage.
                logger.exception(
                    "Transport failed while confirming outbox message %s",
                    message.id,
                )
                return
            self._storage.mark_published(message.id)

    def _relay_batch(self) -> None:
        messages = self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        relayed: list[OutboxMessage] = []
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
                    len(messages) - len(relayed),
                )
                return
            except Exception:
                logger.exception("Failed to relay outbox message %s", message.id)
                self.__register_refusal(message, halted_partition_keys)
                continue
            relayed.append(message)
        if not relayed:
            return
        # The batch is marked published only after flush() returns, so a batch
        # that never left the client stays pending.
        try:
            self._transport.flush()
        except Exception:
            logger.exception(
                "Failed to flush %d relayed outbox messages",
                len(relayed),
            )
            self.__publish_one_at_a_time(relayed, halted_partition_keys)
            return
        for message in relayed:
            self._storage.mark_published(message.id)


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

    async def __register_refusal(
        self,
        message: OutboxMessage,
        halted_partition_keys: set[str],
    ) -> None:
        """Spend one retry on a refused message, or abandon it when none is left.

        A message whose budget is spent will never be fetched again, so it is
        abandoned rather than left behind: that releases its partition key,
        which would otherwise wait forever on a message nobody will retry, and
        keeps the record findable. A message that still has budget holds its key
        back until it is delivered, so nothing of that key overtakes it.
        """
        if message.retry_count + 1 >= self._config.max_retry_count:
            await self._storage.mark_abandoned(message.id)
            return
        await self._storage.increment_retry(message.id)
        if message.partition_key is not None:
            halted_partition_keys.add(message.partition_key)

    async def __publish_one_at_a_time(
        self,
        messages: list[OutboxMessage],
        halted_partition_keys: set[str],
    ) -> None:
        """Replay a batch whose flush failed, confirming one message at a time.

        A batch flush reports that the broker refused something but not what, so
        neither the retry budget nor the partition key hold-back can be aimed
        without replaying. Confirming one message per flush puts the broker's
        verdict on the message that earned it: the refused message spends its
        budget and holds back the rest of its key, while its neighbours publish.
        Only a refusal counts — a transport that cannot reach the broker at all
        stops the replay untouched, because an outage is no message's fault.
        The replay can re-deliver a record the failed flush had already accepted
        — delivery stays at-least-once, which consumers already assume.
        """
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
                await self._transport.flush()
            except EventDeliveryRejectedError:
                logger.exception("Broker refused outbox message %s", message.id)
                await self.__register_refusal(message, halted_partition_keys)
                continue
            except Exception:
                # The transport itself is failing — a closed client, a lost
                # connection, a timeout. That is no single message's fault, so
                # the rest of the batch is left pending instead of spending
                # budgets that would abandon healthy messages during an outage.
                logger.exception(
                    "Transport failed while confirming outbox message %s",
                    message.id,
                )
                return
            await self._storage.mark_published(message.id)

    async def _relay_batch(self) -> None:
        messages = await self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        relayed: list[OutboxMessage] = []
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
                    len(messages) - len(relayed),
                )
                return
            except Exception:
                logger.exception("Failed to relay outbox message %s", message.id)
                await self.__register_refusal(message, halted_partition_keys)
                continue
            relayed.append(message)
        if not relayed:
            return
        # The batch is marked published only after flush() returns, so a batch
        # that never left the client stays pending.
        try:
            await self._transport.flush()
        except Exception:
            logger.exception(
                "Failed to flush %d relayed outbox messages",
                len(relayed),
            )
            await self.__publish_one_at_a_time(relayed, halted_partition_keys)
            return
        for message in relayed:
            await self._storage.mark_published(message.id)
