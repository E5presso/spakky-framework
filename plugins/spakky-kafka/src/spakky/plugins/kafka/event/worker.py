"""Per-subscriber Kafka workers.

A worker is everything Kafka does for one subscriber: its consumer client in
its own consumer group, its poll loop, the partitions it paused for a waiting
message, the retry state it remembers, and its retry and dead-letter records.
Workers share nothing, so a subscriber that fails or falls behind never holds
back another one.
"""

from asyncio import Event as AsyncEvent
from asyncio import wait_for
from logging import getLogger
from threading import Event
from time import monotonic, time
from typing import Any, cast

from aiokafka import AIOKafkaProducer
from confluent_kafka import (
    OFFSET_BEGINNING,
    Consumer,
    KafkaException,
    Message,
    Producer,
    TopicPartition,
)
from confluent_kafka.admin import ClusterMetadata
from confluent_kafka.aio import AIOConsumer
from pydantic import TypeAdapter, ValidationError
from spakky.domain.models.event import AbstractEvent
from spakky.event.delivery import (
    AsyncSubscriptionDelivery,
    DeliveryCompleted,
    DeliveryDeadLettered,
    DeliveryDeferred,
    DeliveryHeaders,
    DeliveryOutcome,
    DeliveryRetry,
    DeliveryState,
    EventRouting,
    RegisteredEventHandler,
    RetryMode,
    SubscriptionDelivery,
)
from spakky.event.error import InvalidDeliveryHeaderError, InvalidMessageError
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
)
from spakky.event.redrive import RedriveResult
from spakky.event.subscription import SubscriberName
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.kafka.auth import KAFKA_AUTH_HEADERS_PARAMETER
from spakky.plugins.kafka.common.config import (
    AutoOffsetResetType,
    KafkaConnectionConfig,
)
from spakky.plugins.kafka.common.constants import (
    ASSIGNMENT_OFFSET_LOOKUP_TIMEOUT,
    KafkaGroupId,
    KafkaTopic,
)
from spakky.plugins.kafka.event.records import (
    ConsumedRecord,
    KafkaDeadLetters,
    KafkaDeliveryHeaders,
    KafkaDeliveryReport,
    PartitionFence,
    PartitionKey,
    RecordCoordinates,
)

logger = getLogger(__name__)


class KafkaSubscriberWorker:
    """Reads, retries, dead-letters and redrives for one synchronous subscriber."""

    config: KafkaConnectionConfig
    subscriber: SubscriberName | None
    """Subscriber served by this worker; None is the unnamed subscriber."""

    group_id: KafkaGroupId
    deliveries: dict[KafkaTopic, SubscriptionDelivery]
    """Subscriptions of this subscriber keyed by event topic."""

    adapters: dict[KafkaTopic, TypeAdapter[AbstractEvent]]
    retry_topics: dict[KafkaTopic, KafkaTopic]
    """Event topic of every retry topic this subscriber reads; empty unless delayed."""

    consumer: Consumer
    """Consumer client of this subscriber, bound by `open` for the service lifetime."""

    producer: Producer
    """Retry and dead-letter producer, bound by `open` for the service lifetime."""

    propagator: ITracePropagator | None
    """Trace propagator; None when tracing is not installed."""

    # Any: handlers of one subscriber are registered per concrete event type.
    _auth_boundary_handlers: set[EventHandlerCallback[Any]]
    _fences: dict[PartitionKey, PartitionFence]
    _states: dict[RecordCoordinates, DeliveryState]

    def __init__(
        self,
        config: KafkaConnectionConfig,
        subscriber: SubscriberName | None,
        auth_boundary_handlers: set[EventHandlerCallback[Any]],
    ) -> None:
        self.config = config
        self.subscriber = subscriber
        self.group_id = config.subscriber_group_id(subscriber)
        self.deliveries = {}
        self.adapters = {}
        self.retry_topics = {}
        self.propagator = None
        self._auth_boundary_handlers = auth_boundary_handlers
        self._fences = {}
        self._states = {}

    def add(self, delivery: SubscriptionDelivery) -> None:
        """Serve one more event subscription of this subscriber."""
        topic = EventRouting.name_of(delivery.event_type)
        if topic in self.deliveries:
            return
        self.deliveries[topic] = delivery
        # TypeAdapter is invariant; the registry is keyed by the event topic.
        self.adapters[topic] = cast(
            TypeAdapter[AbstractEvent], TypeAdapter(delivery.event_type)
        )
        if self.config.retry.mode is RetryMode.DELAYED:
            self.retry_topics[self.config.retry_topic(topic, self.subscriber)] = topic

    @property
    def subscribed_topics(self) -> list[KafkaTopic]:
        """Topics this subscriber reads: its event topics and its retry topics."""
        return [*self.deliveries, *self.retry_topics]

    @property
    def managed_topics(self) -> list[KafkaTopic]:
        """Topics this subscriber needs to exist, dead-letter topics included."""
        return [
            *self.subscribed_topics,
            *(
                self.config.dead_letter_topic(topic, self.subscriber)
                for topic in self.deliveries
            ),
        ]

    def open(self) -> None:
        """Open this subscriber's clients and join its consumer group."""
        self.consumer = Consumer(
            self.config.subscriber_consumer_configuration(self.subscriber),
            logger=logger,
        )
        self.producer = Producer(self.config.producer_configuration_dict, logger=logger)
        self.consumer.subscribe(
            topics=self.subscribed_topics,
            on_assign=self._on_assign,
            on_revoke=self._forget,
            on_lost=self._forget,
        )

    def run(self, stop_event: Event) -> None:
        """Poll and deliver until the service is stopped.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message stays uncommitted and polling ends.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable; the message stays uncommitted and polling ends.
        """
        try:
            while not stop_event.is_set():
                self._resume_due()
                message: Message | None = self.consumer.poll(
                    timeout=self.config.poll_timeout
                )
                if message is None or stop_event.is_set():
                    continue
                self._handle(message)
        except Exception:
            logger.exception(f"Subscriber group {self.group_id} stopped consuming")
            raise

    def close(self) -> None:
        """Flush pending records and leave the consumer group.

        The flush is bounded so an unreachable broker cannot block shutdown.
        """
        self.producer.flush(self.config.dead_letter_delivery_timeout)
        self.consumer.close()

    def redrive(self, origin: KafkaTopic, limit: int | None) -> RedriveResult:
        """Deliver this subscriber's dead letters of one event topic again.

        The dead-letter topic is read through a dedicated group, up to the end
        offsets seen when the call starts. A dead letter whose handlers now
        complete is consumed by committing its offset. One that fails again is
        published to the end of the dead-letter topic with fresh metadata before
        its offset is committed, so it stays available for a later redrive.

        Args:
            origin: Event topic whose dead letters are redriven.
            limit: Most dead letters to take; None takes all stored at the start.

        Returns:
            Counts of dead letters that completed and that failed again.
        """
        delivery = self.deliveries[origin]
        topic = self.config.dead_letter_topic(origin, self.subscriber)
        consumer = Consumer(
            self.config.redrive_consumer_configuration(self.subscriber),
            logger=logger,
        )
        producer = Producer(self.config.producer_configuration_dict, logger=logger)
        succeeded = 0
        failed = 0
        try:
            ends = self._redrive_range(consumer, topic)
            deadline = monotonic() + self.config.redrive_timeout
            while ends and (limit is None or succeeded + failed < limit):
                if monotonic() >= deadline:
                    logger.warning(
                        f"Redrive of {topic} stopped: no dead letter arrived for "
                        f"{self.config.redrive_timeout}s"
                    )
                    break
                message: Message | None = consumer.poll(
                    timeout=self.config.poll_timeout
                )
                if message is None:
                    continue
                error = message.error()
                if error is not None:
                    logger.error(f"Redrive consumer error on {topic}: {error}")
                    continue
                try:
                    record = ConsumedRecord.from_message(message)
                except InvalidMessageError:
                    logger.warning(
                        "Received message with no topic, partition or offset."
                    )
                    continue
                end = ends.get(record.partition)
                if end is None:
                    continue
                if record.offset >= end - 1:
                    # 이 호출이 시작될 때 있던 마지막 레코드까지 읽었다.
                    del ends[record.partition]
                    consumer.pause([TopicPartition(topic, record.partition)])
                if record.offset >= end:
                    continue
                outcome = self._attempt(
                    delivery,
                    origin,
                    record,
                    DeliveryState(
                        pending=KafkaDeliveryHeaders.redrive_pending(record.headers)
                    ),
                )
                if isinstance(outcome, DeliveryCompleted):
                    succeeded += 1
                else:
                    failed += 1
                    headers = KafkaDeliveryHeaders.dead_letter(
                        record,
                        origin,
                        True,
                        self.group_id,
                        KafkaDeadLetters.after_redrive(
                            origin,
                            self.subscriber,
                            outcome,
                            KafkaDeliveryHeaders.previous_attempts(record.headers),
                        ),
                    )
                    if not self._publish(producer, topic, record, headers):
                        # 다시 저장하지 못한 dead letter는 커밋하지 않고 제자리에 둔다.
                        break
                self._commit(consumer, record)
                deadline = monotonic() + self.config.redrive_timeout
        finally:
            consumer.close()
        return RedriveResult(succeeded=succeeded, failed=failed)

    def _redrive_range(self, consumer: Consumer, topic: KafkaTopic) -> dict[int, int]:
        """Assign the unread part of a dead-letter topic and return its end offsets.

        Returns:
            End offset per partition that still holds unread dead letters.
        """
        timeout = self.config.redrive_timeout
        metadata: ClusterMetadata = consumer.list_topics(topic, timeout=timeout)
        topic_metadata = metadata.topics.get(topic)
        if topic_metadata is None:
            return {}
        committed = consumer.committed(
            [
                TopicPartition(topic, partition)
                for partition in topic_metadata.partitions
            ],
            timeout=timeout,
        )
        ends: dict[int, int] = {}
        assignment: list[TopicPartition] = []
        for position in committed:
            low, high = consumer.get_watermark_offsets(
                TopicPartition(topic, position.partition), timeout=timeout
            )
            start = max(position.offset, low)
            if start >= high:
                continue
            ends[position.partition] = high
            assignment.append(TopicPartition(topic, position.partition, start))
        consumer.assign(assignment)
        return ends

    def _handle(self, message: Message) -> None:
        """Deliver one polled message and apply the outcome to the broker."""
        error = message.error()
        if error is not None:
            logger.error(f"Consumer error: {error}")
            return
        try:
            record = ConsumedRecord.from_message(message)
        except InvalidMessageError:
            logger.warning("Received message with no topic, partition or offset.")
            return
        if record.partition_key in self._fences:
            # A prefetched record can arrive after pause. The saved rewind offset
            # remains authoritative, so never dispatch or commit past it.
            return
        carried = record.topic in self.retry_topics
        origin = self.retry_topics.get(record.topic, record.topic)
        delivery = self.deliveries.get(origin)
        if delivery is None:
            logger.warning(f"Received message for unknown event type: {record.topic}")
            return
        state = self._states.get(record.coordinates)
        if carried:
            try:
                due_in = KafkaDeliveryHeaders.not_before(record.headers) - time()
                if state is None:
                    state = DeliveryState.from_headers(record.headers)
            except InvalidDeliveryHeaderError as header_error:
                logger.error(
                    f"Cannot read retry state of a record from {record.topic}: "
                    f"{header_error}"
                )
                self._settle(
                    record,
                    origin,
                    carried,
                    KafkaDeadLetters.undeliverable(
                        origin,
                        self.subscriber,
                        [handler.name for handler in delivery.handlers],
                        DeliveryState().attempt,
                        header_error,
                    ),
                )
                return
            if due_in > 0:
                # 아직 때가 되지 않은 재시도는 시도 횟수 없이 기다린다.
                self._fence(record.position, due_in)
                return
        self._settle(
            record, origin, carried, self._attempt(delivery, origin, record, state)
        )

    def _attempt(
        self,
        delivery: SubscriptionDelivery,
        origin: KafkaTopic,
        record: ConsumedRecord,
        state: DeliveryState | None,
    ) -> DeliveryOutcome:
        """Run one delivery attempt of a record inside its trace context.

        Args:
            delivery: Subscription the record belongs to.
            origin: Event topic the record belongs to.
            record: Record to deliver.
            state: Retry state of the record; None is a first delivery.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable, which is not a verdict about this message.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, which is not a verdict about this message.
        """
        if self.propagator is not None:
            parent = self.propagator.extract(record.headers)
            TraceContext.set(
                parent.child() if parent is not None else TraceContext.new_root()
            )
        try:
            if record.value is None:
                logger.warning(f"Received empty message for event type: {origin}")
                return DeliveryCompleted()
            try:
                event = self.adapters[origin].validate_json(record.value)
            except ValidationError as error:
                # 역직렬화 실패는 같은 본문으로 재시도해도 결과가 같으므로 즉시 보낸다.
                logger.error(f"Cannot deserialize message from topic {origin}: {error}")
                return KafkaDeadLetters.undeliverable(
                    origin,
                    self.subscriber,
                    [handler.name for handler in delivery.handlers],
                    (state or DeliveryState()).attempt,
                    error,
                )
            return delivery.deliver(
                event,
                state,
                lambda handler, delivered: self._invoke(
                    handler, delivered, record.headers
                ),
            )
        finally:
            if self.propagator is not None:
                TraceContext.clear()

    def _invoke(
        self,
        handler: RegisteredEventHandler[EventHandlerCallback[Any]],
        event: AbstractEvent,
        headers: DeliveryHeaders,
    ) -> None:
        """Call a handler, handing the record headers to auth-boundary endpoints."""
        if handler.callback in self._auth_boundary_handlers:
            handler.callback(event, **{KAFKA_AUTH_HEADERS_PARAMETER: headers})
            return
        handler.callback(event)

    def _settle(
        self,
        record: ConsumedRecord,
        origin: KafkaTopic,
        carried: bool,
        outcome: DeliveryOutcome,
    ) -> None:
        """Map a delivery outcome onto offsets, pauses and published records.

        The offset moves only once the outcome is stored somewhere else: a
        message that still waits, or whose retry or dead-letter record did not
        reach the broker, stays uncommitted and comes back.
        """
        match outcome:
            case DeliveryCompleted():
                self._states.pop(record.coordinates, None)
                self._commit(self.consumer, record)
            case DeliveryDeferred(state=state, retry_after=retry_after):
                self._states[record.coordinates] = state
                self._fence(record.position, retry_after)
            case DeliveryRetry(state=state, delay=delay):
                if self.config.retry.mode is RetryMode.DELAYED and self._publish(
                    self.producer,
                    self.config.retry_topic(origin, self.subscriber),
                    record,
                    KafkaDeliveryHeaders.retry(
                        record, origin, carried, state, time() + delay
                    ),
                ):
                    self._states.pop(record.coordinates, None)
                    self._commit(self.consumer, record)
                    return
                # 제자리 재시도: 커밋하지 않고 상태를 기억한 채 파티션을 멈춘다.
                self._states[record.coordinates] = state
                self._fence(record.position, delay)
            case DeliveryDeadLettered(  # pragma: no branch - 전수 분기, 미매치 불가
                dead_letter=dead_letter
            ):
                if self._publish(
                    self.producer,
                    self.config.dead_letter_topic(origin, self.subscriber),
                    record,
                    KafkaDeliveryHeaders.dead_letter(
                        record, origin, carried, self.group_id, dead_letter
                    ),
                ):
                    self._states.pop(record.coordinates, None)
                    self._commit(self.consumer, record)
                    return
                self._rewind(record.position)

    def _publish(
        self,
        producer: Producer,
        topic: KafkaTopic,
        record: ConsumedRecord,
        headers: DeliveryHeaders,
    ) -> bool:
        """Copy a record to a retry or dead-letter topic and confirm delivery.

        The original body and key are forwarded unchanged.

        Returns:
            Whether the broker confirmed the copy. `False` means the record may
            be stored nowhere else, so the caller must not commit its offset.
        """
        report = KafkaDeliveryReport(topic)
        encoded: dict[str, bytes | str | None] = {**headers}
        try:
            producer.produce(
                topic=topic,
                value=record.value,
                key=record.key,
                headers=encoded,
                callback=report.on_delivery,
            )
        except (BufferError, KafkaException) as delivery_error:
            # produce() rejects a record over `message.max.bytes` and a full local
            # queue synchronously. This runs on the poll thread, so an escaping
            # exception would kill consumption while stop() still looks clean.
            logger.error(f"Delivery to {topic} failed: {delivery_error}")
            return False
        undelivered = producer.flush(self.config.dead_letter_delivery_timeout)
        if undelivered:
            logger.error(
                f"Record for {topic} still unsent after "
                f"{self.config.dead_letter_delivery_timeout}s"
            )
            return False
        return report.delivered

    def _commit(self, consumer: Consumer, record: ConsumedRecord) -> None:
        """Advance the committed offset past `record`.

        A commit can be rejected while the consumer group rebalances or the
        broker is unreachable. Letting that escape would end the poll loop, so
        the rejection is logged and the next settled record commits a higher
        offset in its place.
        """
        try:
            committed = consumer.commit(
                offsets=[record.next_position], asynchronous=False
            )
        except KafkaException as error:
            logger.error(f"Offset commit failed for {record.topic}: {error}")
            return
        for position in committed:
            if position.error is not None:
                logger.error(
                    f"Offset commit rejected for {position.topic} "
                    f"[{position.partition}]: {position.error}"
                )

    def _rewind(self, position: TopicPartition) -> None:
        """Move the consume position back so the next poll returns that record.

        Leaving the offset uncommitted is not enough on its own: the consumer's
        in-memory position has already moved past the record, so the next
        record that succeeds would commit an offset beyond the failed one.
        """
        try:
            self.consumer.seek(position)
        except KafkaException as error:
            logger.error(
                f"Cannot rewind {position.topic} [{position.partition}] to offset "
                f"{position.offset}, message is not retryable: {error}"
            )

    def _on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        """Forget stale state and never skip a retry record nobody consumed yet.

        Retry topics are written only by this subscriber, so every record on a
        retry partition without a committed offset is still waiting for it. The
        user's `auto.offset.reset` must not decide about those: under `latest`
        a retry published before a restart would be skipped, and under `none`
        the partition could not start at all. Such partitions therefore start
        at the beginning. Event topics keep following the configured policy.

        The assignment is replaced with `assign`, which matches the eager
        rebalance protocol of the default assignors this plugin configures.

        Raises:
            KafkaException: The committed offsets cannot be read. Starting
                anyway could skip a waiting retry, so the poll loop ends.
        """
        self._forget(consumer, partitions)
        if self.config.auto_offset_reset is AutoOffsetResetType.EARLIEST:
            return
        waiting = [
            TopicPartition(position.topic, position.partition)
            for position in partitions
            if position.topic in self.retry_topics
        ]
        if not waiting:
            return
        unread = {
            (position.topic, position.partition)
            for position in consumer.committed(
                waiting, timeout=ASSIGNMENT_OFFSET_LOOKUP_TIMEOUT
            )
            if position.offset < 0
        }
        if not unread:
            return
        consumer.assign(
            [
                TopicPartition(position.topic, position.partition, OFFSET_BEGINNING)
                if (position.topic, position.partition) in unread
                else position
                for position in partitions
            ]
        )

    def _forget(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        """Forget timers and retry state on assignment, revocation or lost ownership.

        librdkafka retains its default assignment handling; this callback does
        not commit, assign or unassign. A new owner starts at the broker offset
        and delivers the waiting record as a first attempt.
        """
        for position in partitions:
            self._fences.pop((position.topic, position.partition), None)
            for coordinates in list(self._states):
                if coordinates[:2] == (position.topic, position.partition):
                    del self._states[coordinates]

    def _fence(self, position: TopicPartition, delay: float) -> None:
        """Fence this partition before trying to pause and rewind it."""
        self._fences[(position.topic, position.partition)] = PartitionFence(
            position=position, deadline=monotonic() + delay
        )
        try:
            self.consumer.pause([position])
            self.consumer.seek(position)
        except KafkaException as error:
            # Keep the fence even if ownership is changing. Poll delivers the
            # rebalance callback; a due retry rechecks seek before resuming.
            logger.warning("Cannot pause waiting partition %s: %s", position, error)

    def _resume_due(self) -> None:
        """Resume due partitions without sleeping in a handler or blocking poll."""
        now = monotonic()
        for key, fence in list(self._fences.items()):
            if fence.deadline > now:
                continue
            try:
                self.consumer.seek(fence.position)
                self.consumer.resume([fence.position])
            except KafkaException as error:
                logger.warning(
                    "Cannot resume waiting partition %s: %s", fence.position, error
                )
                continue
            del self._fences[key]


class AsyncKafkaSubscriberWorker:
    """Reads, retries, dead-letters and redrives for one asynchronous subscriber."""

    config: KafkaConnectionConfig
    subscriber: SubscriberName | None
    """Subscriber served by this worker; None is the unnamed subscriber."""

    group_id: KafkaGroupId
    deliveries: dict[KafkaTopic, AsyncSubscriptionDelivery]
    """Subscriptions of this subscriber keyed by event topic."""

    adapters: dict[KafkaTopic, TypeAdapter[AbstractEvent]]
    retry_topics: dict[KafkaTopic, KafkaTopic]
    """Event topic of every retry topic this subscriber reads; empty unless delayed."""

    consumer: AIOConsumer
    """Consumer client of this subscriber, bound by `open` for the service lifetime."""

    producer: AIOKafkaProducer
    """Retry and dead-letter producer, bound by `open` for the service lifetime."""

    propagator: ITracePropagator | None
    """Trace propagator; None when tracing is not installed."""

    # Any: handlers of one subscriber are registered per concrete event type.
    _auth_boundary_handlers: set[AsyncEventHandlerCallback[Any]]
    _fences: dict[PartitionKey, PartitionFence]
    _states: dict[RecordCoordinates, DeliveryState]

    def __init__(
        self,
        config: KafkaConnectionConfig,
        subscriber: SubscriberName | None,
        auth_boundary_handlers: set[AsyncEventHandlerCallback[Any]],
    ) -> None:
        self.config = config
        self.subscriber = subscriber
        self.group_id = config.subscriber_group_id(subscriber)
        self.deliveries = {}
        self.adapters = {}
        self.retry_topics = {}
        self.propagator = None
        self._auth_boundary_handlers = auth_boundary_handlers
        self._fences = {}
        self._states = {}

    def add(self, delivery: AsyncSubscriptionDelivery) -> None:
        """Serve one more event subscription of this subscriber."""
        topic = EventRouting.name_of(delivery.event_type)
        if topic in self.deliveries:
            return
        self.deliveries[topic] = delivery
        # TypeAdapter is invariant; the registry is keyed by the event topic.
        self.adapters[topic] = cast(
            TypeAdapter[AbstractEvent], TypeAdapter(delivery.event_type)
        )
        if self.config.retry.mode is RetryMode.DELAYED:
            self.retry_topics[self.config.retry_topic(topic, self.subscriber)] = topic

    @property
    def subscribed_topics(self) -> list[KafkaTopic]:
        """Topics this subscriber reads: its event topics and its retry topics."""
        return [*self.deliveries, *self.retry_topics]

    @property
    def managed_topics(self) -> list[KafkaTopic]:
        """Topics this subscriber needs to exist, dead-letter topics included."""
        return [
            *self.subscribed_topics,
            *(
                self.config.dead_letter_topic(topic, self.subscriber)
                for topic in self.deliveries
            ),
        ]

    async def open(self) -> None:
        """Open this subscriber's clients and join its consumer group."""
        self.consumer = AIOConsumer(
            self.config.subscriber_consumer_configuration(self.subscriber)
        )
        self.producer = AIOKafkaProducer(
            **self.config.async_producer_configuration_dict
        )
        await self.producer.start()
        await self.consumer.subscribe(
            topics=self.subscribed_topics,
            on_assign=self._on_assign,
            on_revoke=self._forget,
            on_lost=self._forget,
        )

    async def run(self, stop_event: AsyncEvent) -> None:
        """Poll and deliver until the service is stopped.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message stays uncommitted and polling ends.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable; the message stays uncommitted and polling ends.
        """
        try:
            while not stop_event.is_set():
                await self._resume_due()
                message: Message | None = await self.consumer.poll(
                    timeout=self.config.poll_timeout
                )
                if message is None or stop_event.is_set():
                    continue
                await self._handle(message)
        except Exception:
            logger.exception(f"Subscriber group {self.group_id} stopped consuming")
            raise

    async def close(self) -> None:
        """Flush pending records and leave the consumer group."""
        await self.producer.stop()
        await self.consumer.close()

    async def redrive(self, origin: KafkaTopic, limit: int | None) -> RedriveResult:
        """Deliver this subscriber's dead letters of one event topic again.

        The dead-letter topic is read through a dedicated group, up to the end
        offsets seen when the call starts. A dead letter whose handlers now
        complete is consumed by committing its offset. One that fails again is
        published to the end of the dead-letter topic with fresh metadata before
        its offset is committed, so it stays available for a later redrive.

        Args:
            origin: Event topic whose dead letters are redriven.
            limit: Most dead letters to take; None takes all stored at the start.

        Returns:
            Counts of dead letters that completed and that failed again.
        """
        delivery = self.deliveries[origin]
        topic = self.config.dead_letter_topic(origin, self.subscriber)
        consumer = AIOConsumer(
            self.config.redrive_consumer_configuration(self.subscriber)
        )
        producer = AIOKafkaProducer(**self.config.async_producer_configuration_dict)
        succeeded = 0
        failed = 0
        try:
            await producer.start()
            ends = await self._redrive_range(consumer, topic)
            deadline = monotonic() + self.config.redrive_timeout
            while ends and (limit is None or succeeded + failed < limit):
                if monotonic() >= deadline:
                    logger.warning(
                        f"Redrive of {topic} stopped: no dead letter arrived for "
                        f"{self.config.redrive_timeout}s"
                    )
                    break
                message: Message | None = await consumer.poll(
                    timeout=self.config.poll_timeout
                )
                if message is None:
                    continue
                error = message.error()
                if error is not None:
                    logger.error(f"Redrive consumer error on {topic}: {error}")
                    continue
                try:
                    record = ConsumedRecord.from_message(message)
                except InvalidMessageError:
                    logger.warning(
                        "Received message with no topic, partition or offset."
                    )
                    continue
                end = ends.get(record.partition)
                if end is None:
                    continue
                if record.offset >= end - 1:
                    # 이 호출이 시작될 때 있던 마지막 레코드까지 읽었다.
                    del ends[record.partition]
                    await consumer.pause([TopicPartition(topic, record.partition)])
                if record.offset >= end:
                    continue
                outcome = await self._attempt(
                    delivery,
                    origin,
                    record,
                    DeliveryState(
                        pending=KafkaDeliveryHeaders.redrive_pending(record.headers)
                    ),
                )
                if isinstance(outcome, DeliveryCompleted):
                    succeeded += 1
                else:
                    failed += 1
                    headers = KafkaDeliveryHeaders.dead_letter(
                        record,
                        origin,
                        True,
                        self.group_id,
                        KafkaDeadLetters.after_redrive(
                            origin,
                            self.subscriber,
                            outcome,
                            KafkaDeliveryHeaders.previous_attempts(record.headers),
                        ),
                    )
                    if not await self._publish(producer, topic, record, headers):
                        # 다시 저장하지 못한 dead letter는 커밋하지 않고 제자리에 둔다.
                        break
                await self._commit(consumer, record)
                deadline = monotonic() + self.config.redrive_timeout
        finally:
            await producer.stop()
            await consumer.close()
        return RedriveResult(succeeded=succeeded, failed=failed)

    async def _redrive_range(
        self, consumer: AIOConsumer, topic: KafkaTopic
    ) -> dict[int, int]:
        """Assign the unread part of a dead-letter topic and return its end offsets.

        Returns:
            End offset per partition that still holds unread dead letters.
        """
        timeout = self.config.redrive_timeout
        metadata: ClusterMetadata = await consumer.list_topics(topic, timeout=timeout)
        topic_metadata = metadata.topics.get(topic)
        if topic_metadata is None:
            return {}
        committed: list[TopicPartition] = await consumer.committed(
            [
                TopicPartition(topic, partition)
                for partition in topic_metadata.partitions
            ],
            timeout=timeout,
        )
        ends: dict[int, int] = {}
        assignment: list[TopicPartition] = []
        for position in committed:
            watermarks: tuple[int, int] = await consumer.get_watermark_offsets(
                TopicPartition(topic, position.partition), timeout=timeout
            )
            low, high = watermarks
            start = max(position.offset, low)
            if start >= high:
                continue
            ends[position.partition] = high
            assignment.append(TopicPartition(topic, position.partition, start))
        await consumer.assign(assignment)
        return ends

    async def _handle(self, message: Message) -> None:
        """Deliver one polled message and apply the outcome to the broker."""
        error = message.error()
        if error is not None:
            logger.error(f"Consumer error: {error}")
            return
        try:
            record = ConsumedRecord.from_message(message)
        except InvalidMessageError:
            logger.warning("Received message with no topic, partition or offset.")
            return
        if record.partition_key in self._fences:
            # A prefetched record can arrive after pause. The saved rewind offset
            # remains authoritative, so never dispatch or commit past it.
            return
        carried = record.topic in self.retry_topics
        origin = self.retry_topics.get(record.topic, record.topic)
        delivery = self.deliveries.get(origin)
        if delivery is None:
            logger.warning(f"Received message for unknown event type: {record.topic}")
            return
        state = self._states.get(record.coordinates)
        if carried:
            try:
                due_in = KafkaDeliveryHeaders.not_before(record.headers) - time()
                if state is None:
                    state = DeliveryState.from_headers(record.headers)
            except InvalidDeliveryHeaderError as header_error:
                logger.error(
                    f"Cannot read retry state of a record from {record.topic}: "
                    f"{header_error}"
                )
                await self._settle(
                    record,
                    origin,
                    carried,
                    KafkaDeadLetters.undeliverable(
                        origin,
                        self.subscriber,
                        [handler.name for handler in delivery.handlers],
                        DeliveryState().attempt,
                        header_error,
                    ),
                )
                return
            if due_in > 0:
                # 아직 때가 되지 않은 재시도는 시도 횟수 없이 기다린다.
                await self._fence(record.position, due_in)
                return
        await self._settle(
            record,
            origin,
            carried,
            await self._attempt(delivery, origin, record, state),
        )

    async def _attempt(
        self,
        delivery: AsyncSubscriptionDelivery,
        origin: KafkaTopic,
        record: ConsumedRecord,
        state: DeliveryState | None,
    ) -> DeliveryOutcome:
        """Run one delivery attempt of a record inside its trace context.

        Args:
            delivery: Subscription the record belongs to.
            origin: Event topic the record belongs to.
            record: Record to deliver.
            state: Retry state of the record; None is a first delivery.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable, which is not a verdict about this message.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, which is not a verdict about this message.
        """
        if self.propagator is not None:
            parent = self.propagator.extract(record.headers)
            TraceContext.set(
                parent.child() if parent is not None else TraceContext.new_root()
            )
        try:
            if record.value is None:
                logger.warning(f"Received empty message for event type: {origin}")
                return DeliveryCompleted()
            try:
                event = self.adapters[origin].validate_json(record.value)
            except ValidationError as error:
                # 역직렬화 실패는 같은 본문으로 재시도해도 결과가 같으므로 즉시 보낸다.
                logger.error(f"Cannot deserialize message from topic {origin}: {error}")
                return KafkaDeadLetters.undeliverable(
                    origin,
                    self.subscriber,
                    [handler.name for handler in delivery.handlers],
                    (state or DeliveryState()).attempt,
                    error,
                )
            return await delivery.deliver(
                event,
                state,
                lambda handler, delivered: self._invoke(
                    handler, delivered, record.headers
                ),
            )
        finally:
            if self.propagator is not None:
                TraceContext.clear()

    async def _invoke(
        self,
        handler: RegisteredEventHandler[AsyncEventHandlerCallback[Any]],
        event: AbstractEvent,
        headers: DeliveryHeaders,
    ) -> None:
        """Call a handler, handing the record headers to auth-boundary endpoints."""
        if handler.callback in self._auth_boundary_handlers:
            await handler.callback(event, **{KAFKA_AUTH_HEADERS_PARAMETER: headers})
            return
        await handler.callback(event)

    async def _settle(
        self,
        record: ConsumedRecord,
        origin: KafkaTopic,
        carried: bool,
        outcome: DeliveryOutcome,
    ) -> None:
        """Map a delivery outcome onto offsets, pauses and published records.

        The offset moves only once the outcome is stored somewhere else: a
        message that still waits, or whose retry or dead-letter record did not
        reach the broker, stays uncommitted and comes back.
        """
        match outcome:
            case DeliveryCompleted():
                self._states.pop(record.coordinates, None)
                await self._commit(self.consumer, record)
            case DeliveryDeferred(state=state, retry_after=retry_after):
                self._states[record.coordinates] = state
                await self._fence(record.position, retry_after)
            case DeliveryRetry(state=state, delay=delay):
                if self.config.retry.mode is RetryMode.DELAYED and await self._publish(
                    self.producer,
                    self.config.retry_topic(origin, self.subscriber),
                    record,
                    KafkaDeliveryHeaders.retry(
                        record, origin, carried, state, time() + delay
                    ),
                ):
                    self._states.pop(record.coordinates, None)
                    await self._commit(self.consumer, record)
                    return
                # 제자리 재시도: 커밋하지 않고 상태를 기억한 채 파티션을 멈춘다.
                self._states[record.coordinates] = state
                await self._fence(record.position, delay)
            case DeliveryDeadLettered(  # pragma: no branch - 전수 분기, 미매치 불가
                dead_letter=dead_letter
            ):
                if await self._publish(
                    self.producer,
                    self.config.dead_letter_topic(origin, self.subscriber),
                    record,
                    KafkaDeliveryHeaders.dead_letter(
                        record, origin, carried, self.group_id, dead_letter
                    ),
                ):
                    self._states.pop(record.coordinates, None)
                    await self._commit(self.consumer, record)
                    return
                await self._rewind(record.position)

    async def _publish(
        self,
        producer: AIOKafkaProducer,
        topic: KafkaTopic,
        record: ConsumedRecord,
        headers: DeliveryHeaders,
    ) -> bool:
        """Copy a record to a retry or dead-letter topic and confirm delivery.

        The original body and key are forwarded unchanged. Delivery is awaited
        so a broker rejection is logged rather than lost, and it is bounded so
        one unreachable broker cannot stall the poll loop.

        Returns:
            Whether the broker confirmed the copy. `False` means the record may
            be stored nowhere else, so the caller must not commit its offset.
            An unconfirmed timeout also reports `False`: keeping the message can
            duplicate the copy, which is the recoverable direction.
        """
        try:
            await wait_for(
                producer.send_and_wait(
                    topic=topic,
                    value=record.value,
                    key=record.key,
                    headers=KafkaDeliveryHeaders.encode(headers),
                ),
                timeout=self.config.dead_letter_delivery_timeout,
            )
        except TimeoutError:
            # Only the confirmation wait is abandoned here — the record stays in the
            # producer batch and may still reach the broker, so replaying it by hand
            # can duplicate it. Reported apart from a confirmed refusal.
            logger.error(
                f"Delivery to {topic} unconfirmed after "
                f"{self.config.dead_letter_delivery_timeout}s; "
                "it may still be delivered"
            )
            return False
        except Exception as delivery_error:
            logger.error(f"Delivery to {topic} failed: {delivery_error}")
            return False
        return True

    async def _commit(self, consumer: AIOConsumer, record: ConsumedRecord) -> None:
        """Advance the committed offset past `record`.

        A commit can be rejected while the consumer group rebalances or the
        broker is unreachable. Letting that escape would end the polling task,
        so the rejection is logged and the next settled record commits a higher
        offset in its place.
        """
        try:
            committed: list[TopicPartition] = await consumer.commit(
                offsets=[record.next_position], asynchronous=False
            )
        except KafkaException as error:
            logger.error(f"Offset commit failed for {record.topic}: {error}")
            return
        for position in committed:
            if position.error is not None:
                logger.error(
                    f"Offset commit rejected for {position.topic} "
                    f"[{position.partition}]: {position.error}"
                )

    async def _rewind(self, position: TopicPartition) -> None:
        """Move the consume position back so the next poll returns that record.

        Leaving the offset uncommitted is not enough on its own: the consumer's
        in-memory position has already moved past the record, so the next
        record that succeeds would commit an offset beyond the failed one.
        """
        try:
            await self.consumer.seek(position)
        except KafkaException as error:
            logger.error(
                f"Cannot rewind {position.topic} [{position.partition}] to offset "
                f"{position.offset}, message is not retryable: {error}"
            )

    async def _on_assign(
        self, consumer: AIOConsumer, partitions: list[TopicPartition]
    ) -> None:
        """Forget stale state and never skip a retry record nobody consumed yet.

        Retry topics are written only by this subscriber, so every record on a
        retry partition without a committed offset is still waiting for it. The
        user's `auto.offset.reset` must not decide about those: under `latest`
        a retry published before a restart would be skipped, and under `none`
        the partition could not start at all. Such partitions therefore start
        at the beginning. Event topics keep following the configured policy.

        The assignment is replaced with `assign`, which matches the eager
        rebalance protocol of the default assignors this plugin configures.

        Raises:
            KafkaException: The committed offsets cannot be read. Starting
                anyway could skip a waiting retry, so the poll loop ends.
        """
        await self._forget(consumer, partitions)
        if self.config.auto_offset_reset is AutoOffsetResetType.EARLIEST:
            return
        waiting = [
            TopicPartition(position.topic, position.partition)
            for position in partitions
            if position.topic in self.retry_topics
        ]
        if not waiting:
            return
        committed: list[TopicPartition] = await consumer.committed(
            waiting, timeout=ASSIGNMENT_OFFSET_LOOKUP_TIMEOUT
        )
        unread = {
            (position.topic, position.partition)
            for position in committed
            if position.offset < 0
        }
        if not unread:
            return
        await consumer.assign(
            [
                TopicPartition(position.topic, position.partition, OFFSET_BEGINNING)
                if (position.topic, position.partition) in unread
                else position
                for position in partitions
            ]
        )

    async def _forget(
        self, consumer: AIOConsumer, partitions: list[TopicPartition]
    ) -> None:
        """Forget timers and retry state on assignment, revocation or lost ownership.

        librdkafka retains its default assignment handling; this callback does
        not commit, assign or unassign. A new owner starts at the broker offset
        and delivers the waiting record as a first attempt.
        """
        for position in partitions:
            self._fences.pop((position.topic, position.partition), None)
            for coordinates in list(self._states):
                if coordinates[:2] == (position.topic, position.partition):
                    del self._states[coordinates]

    async def _fence(self, position: TopicPartition, delay: float) -> None:
        """Fence this partition before trying to pause and rewind it."""
        self._fences[(position.topic, position.partition)] = PartitionFence(
            position=position, deadline=monotonic() + delay
        )
        try:
            await self.consumer.pause([position])
            await self.consumer.seek(position)
        except KafkaException as error:
            # Keep the fence even if ownership is changing. Poll delivers the
            # rebalance callback; a due retry rechecks seek before resuming.
            logger.warning("Cannot pause waiting partition %s: %s", position, error)

    async def _resume_due(self) -> None:
        """Resume due partitions without sleeping in a handler or blocking poll."""
        now = monotonic()
        for key, fence in list(self._fences.items()):
            if fence.deadline > now:
                continue
            try:
                await self.consumer.seek(fence.position)
                await self.consumer.resume([fence.position])
            except KafkaException as error:
                logger.warning(
                    "Cannot resume waiting partition %s: %s", fence.position, error
                )
                continue
            del self._fences[key]
