"""Outbox Relay Background Services (sync and async)."""

import logging
from asyncio import AbstractEventLoop, get_running_loop, wait_for
from asyncio import Event as AsyncEvent
from threading import Event
from uuid import UUID

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
from spakky.outbox.relay.wakeup import OutboxRelayWakeup

logger = logging.getLogger(__name__)


@Pod()
class OutboxRelayBackgroundService(AbstractBackgroundService):
    """Relays pending Outbox messages to the transport (sync).

    The relay reads the outbox as soon as a transaction that stored messages
    commits, and every `polling_interval_seconds` to recover what an earlier
    read could not send.
    """

    _storage: IOutboxStorage
    _transport: IEventTransport
    _config: OutboxConfig
    _wakeup: OutboxRelayWakeup
    _wake_event: Event

    def __init__(
        self,
        storage: IOutboxStorage,
        transport: IEventTransport,
        config: OutboxConfig,
        wakeup: OutboxRelayWakeup,
    ) -> None:
        """Initialize with storage, transport, config, and wakeup dependencies."""
        self._storage = storage
        self._transport = transport
        self._config = config
        self._wakeup = wakeup
        self._wake_event = Event()

    @override
    def initialize(self) -> None:
        """Start listening for commits that stored outbox messages."""
        self._wakeup.subscribe(self.wake)

    @override
    def dispose(self) -> None:
        """Stop listening for commits."""
        self._wakeup.unsubscribe(self.wake)

    @override
    def stop(self) -> None:
        """Stop the relay without waiting for the current polling interval."""
        self._stop_event.set()
        self._wake_event.set()
        super().stop()

    def wake(self) -> None:
        """Read the outbox now instead of at the next poll. Thread-safe."""
        self._wake_event.set()

    @override
    def run(self) -> None:
        """Relay pending messages on every wake-up and poll until stopped.

        A failing read is logged and the loop goes on, so one database error
        does not stop delivery until the service restarts.
        """
        while True:
            self._wake_event.clear()
            if self._stop_event.is_set():
                return
            try:
                self._relay_batch()
            except Exception:
                logger.exception("Outbox relay batch failed; retrying at next poll")
            self._wake_event.wait(timeout=self._config.polling_interval_seconds)

    def __register_refusal(
        self,
        message: OutboxMessage,
        halted_partition_keys: set[str],
        settled_ids: set[UUID],
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
            settled_ids.add(message.id)
            return
        self._storage.increment_retry(message.id)
        if message.partition_key is not None:
            halted_partition_keys.add(message.partition_key)

    def __publish_one_at_a_time(
        self,
        messages: list[OutboxMessage],
        halted_partition_keys: set[str],
        settled_ids: set[UUID],
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
                self.__register_refusal(message, halted_partition_keys, settled_ids)
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
            settled_ids.add(message.id)

    def __release_unsettled(
        self,
        messages: list[OutboxMessage],
        settled_ids: set[UUID],
    ) -> None:
        """Release the claims of the messages this read did not settle.

        A message that was neither published nor abandoned — refused with
        budget left, held back behind its partition key, or caught in a
        transport failure — goes back to the queue right away, so the next
        read sends it again instead of waiting for the claim to time out.
        """
        # A failing release must not hide the error or cancellation that ended
        # the read; the claims it could not clear expire after the timeout.
        try:
            for message in messages:
                if message.id not in settled_ids:
                    self._storage.release_claim(message)
        except Exception:
            logger.exception("Failed to release outbox claims; they expire later")

    def _relay_batch(self) -> None:
        messages = self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        settled_ids: set[UUID] = set()
        try:
            self.__relay_claimed(messages, settled_ids)
        finally:
            self.__release_unsettled(messages, settled_ids)

    def __relay_claimed(
        self,
        messages: list[OutboxMessage],
        settled_ids: set[UUID],
    ) -> None:
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
            except EventDeliveryRejectedError:
                logger.exception("Transport rejected outbox message %s", message.id)
                self.__register_refusal(message, halted_partition_keys, settled_ids)
                continue
            except Exception:
                # A transport-wide failure is not attributable to this record.
                # Preserve the whole batch without charging any message's retry
                # budget, just as the one-at-a-time confirmation path does.
                logger.exception(
                    "Transport failed while relaying outbox message %s",
                    message.id,
                )
                return
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
            self.__publish_one_at_a_time(relayed, halted_partition_keys, settled_ids)
            return
        for message in relayed:
            self._storage.mark_published(message.id)
            settled_ids.add(message.id)


@Pod()
class AsyncOutboxRelayBackgroundService(AbstractAsyncBackgroundService):
    """Relays pending Outbox messages to the transport (async).

    The relay reads the outbox as soon as a transaction that stored messages
    commits, and every `polling_interval_seconds` to recover what an earlier
    read could not send.
    """

    _storage: IAsyncOutboxStorage
    _transport: IAsyncEventTransport
    _config: OutboxConfig
    _wakeup: OutboxRelayWakeup
    _wake_event: AsyncEvent
    _loop: AbstractEventLoop | None
    """Loop the relay runs on. None while the relay is not started."""

    def __init__(
        self,
        storage: IAsyncOutboxStorage,
        transport: IAsyncEventTransport,
        config: OutboxConfig,
        wakeup: OutboxRelayWakeup,
    ) -> None:
        """Initialize with async storage, transport, config, and wakeup dependencies."""
        self._storage = storage
        self._transport = transport
        self._config = config
        self._wakeup = wakeup
        self._wake_event = AsyncEvent()
        self._loop = None

    @override
    async def initialize_async(self) -> None:
        """Start listening for commits that stored outbox messages."""
        self._loop = get_running_loop()
        self._wake_event = AsyncEvent()
        self._wakeup.subscribe(self.wake)

    @override
    async def dispose_async(self) -> None:
        """Stop listening for commits."""
        self._wakeup.unsubscribe(self.wake)
        self._loop = None

    @override
    async def stop_async(self) -> None:
        """Stop the relay without waiting for the current polling interval."""
        self._stop_event.set()
        self._wake_event.set()
        await super().stop_async()

    def wake(self) -> None:
        """Read the outbox now instead of at the next poll.

        Safe to call from any thread: a commit in synchronous code running on
        a worker thread wakes the relay on its own event loop. Before the relay
        starts there is no loop to wake, and its first read picks the message up.
        """
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._wake_event.set)

    @override
    async def run_async(self) -> None:
        """Relay pending messages on every wake-up and poll until stopped.

        A failing read is logged and the loop goes on, so one database error
        does not stop delivery until the service restarts.
        """
        while True:
            self._wake_event.clear()
            if self._stop_event.is_set():
                return
            try:
                await self._relay_batch()
            except Exception:
                logger.exception("Outbox relay batch failed; retrying at next poll")
            try:
                await wait_for(
                    self._wake_event.wait(),
                    timeout=self._config.polling_interval_seconds,
                )
            except TimeoutError:
                continue

    async def __register_refusal(
        self,
        message: OutboxMessage,
        halted_partition_keys: set[str],
        settled_ids: set[UUID],
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
            settled_ids.add(message.id)
            return
        await self._storage.increment_retry(message.id)
        if message.partition_key is not None:
            halted_partition_keys.add(message.partition_key)

    async def __publish_one_at_a_time(
        self,
        messages: list[OutboxMessage],
        halted_partition_keys: set[str],
        settled_ids: set[UUID],
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
                await self.__register_refusal(
                    message, halted_partition_keys, settled_ids
                )
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
            settled_ids.add(message.id)

    async def __release_unsettled(
        self,
        messages: list[OutboxMessage],
        settled_ids: set[UUID],
    ) -> None:
        """Release the claims of the messages this read did not settle.

        A message that was neither published nor abandoned — refused with
        budget left, held back behind its partition key, or caught in a
        transport failure — goes back to the queue right away, so the next
        read sends it again instead of waiting for the claim to time out.
        """
        # A failing release must not hide the error or cancellation that ended
        # the read; the claims it could not clear expire after the timeout.
        try:
            for message in messages:
                if message.id not in settled_ids:
                    await self._storage.release_claim(message)
        except Exception:
            logger.exception("Failed to release outbox claims; they expire later")

    async def _relay_batch(self) -> None:
        messages = await self._storage.fetch_pending(
            self._config.batch_size,
            self._config.max_retry_count,
        )
        settled_ids: set[UUID] = set()
        try:
            await self.__relay_claimed(messages, settled_ids)
        finally:
            await self.__release_unsettled(messages, settled_ids)

    async def __relay_claimed(
        self,
        messages: list[OutboxMessage],
        settled_ids: set[UUID],
    ) -> None:
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
            except EventDeliveryRejectedError:
                logger.exception("Transport rejected outbox message %s", message.id)
                await self.__register_refusal(
                    message, halted_partition_keys, settled_ids
                )
                continue
            except Exception:
                # A transport-wide failure is not attributable to this record.
                # Preserve the whole batch without charging any message's retry
                # budget, just as the one-at-a-time confirmation path does.
                logger.exception(
                    "Transport failed while relaying outbox message %s",
                    message.id,
                )
                return
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
            await self.__publish_one_at_a_time(
                relayed, halted_partition_keys, settled_ids
            )
            return
        for message in relayed:
            await self._storage.mark_published(message.id)
            settled_ids.add(message.id)
