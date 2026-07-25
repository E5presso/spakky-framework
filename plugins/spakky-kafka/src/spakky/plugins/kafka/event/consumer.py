from asyncio import wait_for
from enum import StrEnum
from logging import getLogger
from typing import Any, cast

from spakky.auth import (
    AuthContextNotFoundError,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthVerificationProviderUnavailableError,
)
from aiokafka import AIOKafkaProducer
from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    Message,
    Producer,
    TopicPartition,
)
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.aio import AIOConsumer
from pydantic import TypeAdapter, ValidationError
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.domain.models.event import AbstractEvent
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator
from typing import override

from spakky.plugins.kafka.auth import KAFKA_AUTH_HEADERS_PARAMETER
from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.common.constants import DeadLetterHeaderKey

logger = getLogger(__name__)


class MessageOutcome(StrEnum):
    """What running the handlers settled about one consumed message.

    The consumer turns this into the offset action that gives the delivery
    guarantee: an offset must never move past a message whose failure is not
    stored anywhere else.
    """

    PROCESSED = "processed"
    """The consumer is done with the message and commits its offset.

    Covers handler success, every failure a retry cannot fix (a refused auth
    boundary, an empty message body), and a failure whose dead-letter record
    reached the broker.
    """

    RETRYABLE = "retryable"
    """The message is still the only copy of its own failure, so it comes back.

    Reached when dead-lettering itself failed. The consumer rewinds its position
    to the message instead of committing, and the next poll delivers it again.
    """


def _event_routing_name(event: type[AbstractEvent]) -> str:
    descriptor = event.__dict__.get("event_name")
    if isinstance(descriptor, property):
        probe = object.__new__(event)
        return cast(str, descriptor.__get__(probe, event))
    return event.__name__


@Pod()
class KafkaEventConsumer(IEventConsumer, AbstractBackgroundService):
    """Synchronous Kafka event consumer that polls messages and dispatches to handlers."""

    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractEvent]]
    type_adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    handlers: dict[type[AbstractEvent], list[EventHandlerCallback[Any]]]
    admin: AdminClient
    consumer: Consumer
    producer: Producer
    """Dead-letter producer, bound by `initialize` for the service lifetime."""
    _propagator: ITracePropagator | None
    _auth_boundary_handlers: set[EventHandlerCallback[Any]]

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self._propagator = None
        self._auth_boundary_handlers = set()
        self.admin = AdminClient(self.config.connection_configuration_dict)
        self.consumer = Consumer(
            self.config.consumer_configuration_dict,
            logger=logger,
        )

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator

    def register_auth_boundary(self, handler: EventHandlerCallback[Any]) -> None:
        """Mark a registered post-processor endpoint as Kafka auth-aware."""
        self._auth_boundary_handlers.add(handler)

    @staticmethod
    def _to_string_headers(
        raw: dict[str, bytes | str | None]
        | list[tuple[str, bytes | str | None]]
        | None,
    ) -> dict[str, str]:
        """Convert Kafka message headers to a string-valued carrier dict.

        Kafka headers may be a list of (key, value) tuples or a dict.
        Values can be bytes, str, or None. This method decodes bytes and
        keeps str values, skipping None.

        Args:
            raw: Raw Kafka headers, or None.

        Returns:
            A dict with string keys and string values.
        """
        if raw is None:
            return {}
        items = raw.items() if isinstance(raw, dict) else raw
        result: dict[str, str] = {}
        for key, value in items:
            if isinstance(value, str):
                result[key] = value
            elif isinstance(value, bytes):
                result[key] = value.decode()
        return result

    def _create_topics(self, topics: list[str]) -> None:
        if not topics:  # pragma: no cover - 등록된 핸들러 없을 때 조기 반환
            return
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:  # pragma: no cover - 모든 토픽이 이미 존재
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
                for topic in topics_to_create
            ]
        )

    @staticmethod
    def _dead_letter_delivery_report(
        error: KafkaError | None,
        message: Message,
    ) -> None:
        """Log the broker verdict on a dead-letter record.

        `Producer.produce` only enqueues, so failures the broker decides —
        authorization refusals and delivery timeouts — surface only here.
        """
        if error is not None:
            logger.error(f"Dead-letter delivery failed for {message.topic()}: {error}")

    def _send_to_dead_letter(
        self,
        topic: str,
        message: Message,
        headers: dict[str, str],
        error: Exception,
    ) -> bool:
        """Forward a message the handlers could not process to its dead-letter topic.

        The original body and key are forwarded unchanged and the decoded original
        headers travel with them, so the record can be replayed from its own
        coordinates.

        Args:
            topic: Topic the failed message was consumed from.
            message: The Kafka message that could not be processed.
            headers: Decoded headers of the original message.
            error: Exception that ended the last processing attempt.

        Returns:
            Whether the dead-letter record reached the broker. `False` means the
            failure is stored nowhere, so the caller must keep the original
            message rather than commit its offset.
        """
        _, original_timestamp = message.timestamp()
        dead_letter_headers: dict[str, bytes | str | None] = {
            **headers,
            DeadLetterHeaderKey.ORIGINAL_TOPIC.value: topic,
            DeadLetterHeaderKey.ORIGINAL_PARTITION.value: str(message.partition()),
            DeadLetterHeaderKey.ORIGINAL_OFFSET.value: str(message.offset()),
            DeadLetterHeaderKey.ORIGINAL_TIMESTAMP.value: str(original_timestamp),
            DeadLetterHeaderKey.CONSUMER_GROUP.value: self.config.group_id,
            DeadLetterHeaderKey.EXCEPTION_TYPE.value: type(error).__name__,
            DeadLetterHeaderKey.EXCEPTION_MESSAGE.value: str(error),
        }
        try:
            self.producer.produce(
                topic=f"{topic}{self.config.dead_letter_topic_suffix}",
                value=message.value(),
                key=message.key(),
                headers=dead_letter_headers,
                callback=self._dead_letter_delivery_report,
            )
        except (BufferError, KafkaException) as delivery_error:
            # produce() rejects a record over `message.max.bytes` and a full local
            # queue synchronously. This runs on the poll thread, so an escaping
            # exception would kill consumption while stop() still looks clean.
            logger.error(f"Dead-letter delivery failed for {topic}: {delivery_error}")
            return False
        undelivered = self.producer.flush(self.config.dead_letter_delivery_timeout)
        if undelivered:
            logger.error(
                f"Dead-letter record for {topic} still unsent after "
                f"{self.config.dead_letter_delivery_timeout}s"
            )
            return False
        return True

    def _invoke_handlers(
        self,
        event_type: type[AbstractEvent],
        event_data: AbstractEvent,
        headers: dict[str, str],
    ) -> None:
        for handler in self.handlers[event_type]:
            if handler in self._auth_boundary_handlers:
                handler(event_data, **{KAFKA_AUTH_HEADERS_PARAMETER: headers})
                continue
            handler(event_data)

    def _dead_letter_outcome(
        self,
        topic: str,
        message: Message,
        headers: dict[str, str],
        error: Exception,
    ) -> MessageOutcome:
        """Decide what happens to the offset of a message the handlers refused.

        The offset may only advance once the failure is stored somewhere else. If
        the dead-letter record never reached the broker, committing would destroy
        the only remaining copy of the event, so the message is kept for another
        attempt instead.
        """
        if self._send_to_dead_letter(topic, message, headers, error):
            return MessageOutcome.PROCESSED
        return MessageOutcome.RETRYABLE

    def _commit_offset(self, message: Message) -> None:
        """Advance the committed offset past `message`.

        A commit can be rejected while the consumer group rebalances or the
        broker is unreachable. Letting that escape would end the poll loop and
        stop every subscription this consumer owns, so the rejection is logged
        and the next processed message commits a higher offset in its place.
        """
        try:
            committed = self.consumer.commit(message=message, asynchronous=False)
        except KafkaException as error:
            logger.error(
                f"Offset commit failed for event type {message.topic()}: {error}"
            )
            return
        for position in committed:
            if position.error is not None:
                logger.error(
                    f"Offset commit rejected for {position.topic} "
                    f"[{position.partition}]: {position.error}"
                )

    def _rewind_to(self, position: TopicPartition) -> None:
        """Move the consume position back so the next poll returns that message.

        Leaving the offset uncommitted is not enough on its own: the consumer's
        in-memory position has already moved past the message, so the next
        message that succeeds would commit an offset beyond the failed one and
        the failure would never come back.
        """
        try:
            self.consumer.seek(position)
        except KafkaException as error:
            logger.error(
                f"Cannot rewind {position.topic} [{position.partition}] to offset "
                f"{position.offset}, message is not retryable: {error}"
            )

    def _dispatch_to_handlers(
        self,
        message: Message,
        topic: str,
        event_type: type[AbstractEvent],
        headers: dict[str, str],
    ) -> MessageOutcome:
        """Run every handler registered for one polled message.

        Returns:
            `PROCESSED` when the consumer is done with the message, `RETRYABLE`
            when the message must be delivered again.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable, which is not a verdict about this message.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, which is not a verdict about this message.
        """
        event_message: bytes | None = message.value()
        if event_message is None:
            logger.warning(f"Received empty message for event type: {topic}")
            return MessageOutcome.PROCESSED
        try:
            event_data = self.type_adapters[event_type].validate_json(event_message)
        except ValidationError as error:
            # 역직렬화 실패는 같은 본문으로 재시도해도 결과가 같으므로 즉시 보낸다.
            logger.error(f"Cannot deserialize message from topic {topic}: {error}")
            return self._dead_letter_outcome(topic, message, headers, error)
        remaining_retries = self.config.max_handler_retries
        while True:
            try:
                self._invoke_handlers(event_type, event_data, headers)
                return MessageOutcome.PROCESSED
            except (
                AuthVerificationProviderUnavailableError,
                AuthRequirementProviderUnavailableError,
            ):
                raise
            except (AuthContextNotFoundError, AuthRequirementDeniedError) as error:
                logger.warning(
                    f"Auth boundary refused message for event type {topic}, "
                    f"discarding it: {error}"
                )
                return MessageOutcome.PROCESSED
            except Exception as error:
                if remaining_retries == 0:
                    logger.error(
                        f"Error processing message for event type {topic}: {error}"
                    )
                    return self._dead_letter_outcome(topic, message, headers, error)
                remaining_retries -= 1
                logger.warning(
                    f"Retrying message for event type {topic} after error: {error}"
                )

    def _route_event_handler(self, message: Message) -> None:
        if message.error():  # pragma: no cover - Kafka 브로커 에러 콜백
            logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        partition: int | None = message.partition()
        offset: int | None = message.offset()
        if (  # pragma: no cover - Kafka 메시지 비정상 상태
            topic is None or partition is None or offset is None
        ):
            logger.warning("Received message with no topic, partition or offset.")
            return
        event_type: type[AbstractEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover - 미등록 이벤트 타입 수신 방어
            logger.warning(f"Received message for unknown event type: {topic}")
            return
        headers = self._to_string_headers(message.headers())
        if self._propagator is not None:
            carrier = headers
            parent = self._propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        try:
            outcome = self._dispatch_to_handlers(message, topic, event_type, headers)
            match outcome:
                case MessageOutcome.PROCESSED:
                    self._commit_offset(message)
                case (
                    MessageOutcome.RETRYABLE
                ):  # pragma: no branch - 전수 분기, 미매치 불가
                    self._rewind_to(TopicPartition(topic, partition, offset))
        finally:
            if self._propagator is not None:
                TraceContext.clear()

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None:
        """Register a handler for the given event type."""
        if event not in self.handlers:
            self.handlers[event] = []
            self.type_adapters[event] = cast(
                TypeAdapter[AbstractEvent], TypeAdapter(event)
            )
            self.type_lookup[_event_routing_name(event)] = event
        self.handlers[event].append(handler)

    @override
    def initialize(self) -> None:
        """Create Kafka topics, open the dead-letter producer, and subscribe."""
        topics: list[str] = [
            _event_routing_name(event_type) for event_type in self.handlers.keys()
        ]
        self.producer = Producer(self.config.producer_configuration_dict, logger=logger)
        self._create_topics(
            topics=topics
            + [f"{topic}{self.config.dead_letter_topic_suffix}" for topic in topics]
        )
        self.consumer.subscribe(topics=topics)

    @override
    def run(self) -> None:
        """Poll Kafka for messages and route them to registered handlers."""
        while not self._stop_event.is_set():
            message: Message | None = self.consumer.poll(
                timeout=self.config.poll_timeout
            )
            if message is None:
                continue
            self._route_event_handler(message)

    @override
    def dispose(self) -> None:
        """Flush pending dead-letter records and close the Kafka consumer.

        The flush is bounded so an unreachable broker cannot block shutdown
        forever; records still queued at that point are reported by the
        delivery callback.
        """
        self.producer.flush(self.config.dead_letter_delivery_timeout)
        self.consumer.close()


@Pod()
class AsyncKafkaEventConsumer(IAsyncEventConsumer, AbstractAsyncBackgroundService):
    """Asynchronous Kafka event consumer that polls messages and dispatches to handlers."""

    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractEvent]]
    type_adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    handlers: dict[type[AbstractEvent], list[AsyncEventHandlerCallback[Any]]]
    admin: AdminClient
    consumer: AIOConsumer
    producer: AIOKafkaProducer
    """Dead-letter producer, bound by `initialize_async` for the service lifetime."""
    _propagator: ITracePropagator | None
    _auth_boundary_handlers: set[AsyncEventHandlerCallback[Any]]

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self._propagator = None
        self._auth_boundary_handlers = set()
        self.admin = AdminClient(self.config.connection_configuration_dict)

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator

    def register_auth_boundary(self, handler: AsyncEventHandlerCallback[Any]) -> None:
        """Mark a registered post-processor endpoint as Kafka auth-aware."""
        self._auth_boundary_handlers.add(handler)

    @staticmethod
    def _to_string_headers(
        raw: dict[str, bytes | str | None]
        | list[tuple[str, bytes | str | None]]
        | None,
    ) -> dict[str, str]:
        """Convert Kafka message headers to a string-valued carrier dict.

        Kafka headers may be a list of (key, value) tuples or a dict.
        Values can be bytes, str, or None. This method decodes bytes and
        keeps str values, skipping None.

        Args:
            raw: Raw Kafka headers, or None.

        Returns:
            A dict with string keys and string values.
        """
        if raw is None:
            return {}
        items = raw.items() if isinstance(raw, dict) else raw
        result: dict[str, str] = {}
        for key, value in items:
            if isinstance(value, str):
                result[key] = value
            elif isinstance(value, bytes):
                result[key] = value.decode()
        return result

    def _create_topics(self, topics: list[str]) -> None:
        if not topics:  # pragma: no cover - 등록된 핸들러 없을 때 조기 반환
            return
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:  # pragma: no cover - 모든 토픽이 이미 존재
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
                for topic in topics_to_create
            ]
        )

    async def _send_to_dead_letter(
        self,
        topic: str,
        message: Message,
        headers: dict[str, str],
        error: Exception,
    ) -> bool:
        """Forward a message the handlers could not process to its dead-letter topic.

        The original body and key are forwarded unchanged and the decoded original
        headers travel with them, so the record can be replayed from its own
        coordinates. Delivery is awaited so a broker rejection is logged rather
        than lost, and it is bounded so one unreachable broker cannot stall the
        poll loop.

        Args:
            topic: Topic the failed message was consumed from.
            message: The Kafka message that could not be processed.
            headers: Decoded headers of the original message.
            error: Exception that ended the last processing attempt.

        Returns:
            Whether the dead-letter record is confirmed at the broker. `False`
            means the failure may be stored nowhere, so the caller must keep the
            original message rather than commit its offset. An unconfirmed
            timeout also reports `False`: keeping the message can duplicate the
            dead-letter record, which is the recoverable direction.
        """
        _, original_timestamp = message.timestamp()
        dead_letter_headers: dict[str, str] = {
            **headers,
            DeadLetterHeaderKey.ORIGINAL_TOPIC.value: topic,
            DeadLetterHeaderKey.ORIGINAL_PARTITION.value: str(message.partition()),
            DeadLetterHeaderKey.ORIGINAL_OFFSET.value: str(message.offset()),
            DeadLetterHeaderKey.ORIGINAL_TIMESTAMP.value: str(original_timestamp),
            DeadLetterHeaderKey.CONSUMER_GROUP.value: self.config.group_id,
            DeadLetterHeaderKey.EXCEPTION_TYPE.value: type(error).__name__,
            DeadLetterHeaderKey.EXCEPTION_MESSAGE.value: str(error),
        }
        try:
            await wait_for(
                self.producer.send_and_wait(
                    topic=f"{topic}{self.config.dead_letter_topic_suffix}",
                    value=message.value(),
                    key=message.key(),
                    headers=[
                        (key, value.encode())
                        for key, value in dead_letter_headers.items()
                    ],
                ),
                timeout=self.config.dead_letter_delivery_timeout,
            )
        except TimeoutError:
            # Only the confirmation wait is abandoned here — the record stays in the
            # producer batch and may still reach the broker, so replaying it by hand
            # can duplicate it. Reported apart from a confirmed refusal.
            logger.error(
                f"Dead-letter delivery for {topic} unconfirmed after "
                f"{self.config.dead_letter_delivery_timeout}s; "
                "it may still be delivered"
            )
            return False
        except Exception as delivery_error:
            logger.error(f"Dead-letter delivery failed for {topic}: {delivery_error}")
            return False
        return True

    async def _invoke_handlers(
        self,
        event_type: type[AbstractEvent],
        event_data: AbstractEvent,
        headers: dict[str, str],
    ) -> None:
        for handler in self.handlers[event_type]:
            if handler in self._auth_boundary_handlers:
                await handler(event_data, **{KAFKA_AUTH_HEADERS_PARAMETER: headers})
                continue
            await handler(event_data)

    async def _dead_letter_outcome(
        self,
        topic: str,
        message: Message,
        headers: dict[str, str],
        error: Exception,
    ) -> MessageOutcome:
        """Decide what happens to the offset of a message the handlers refused.

        The offset may only advance once the failure is stored somewhere else. If
        the dead-letter record is not confirmed at the broker, committing would
        destroy the only remaining copy of the event, so the message is kept for
        another attempt instead.
        """
        if await self._send_to_dead_letter(topic, message, headers, error):
            return MessageOutcome.PROCESSED
        return MessageOutcome.RETRYABLE

    async def _commit_offset(self, message: Message) -> None:
        """Advance the committed offset past `message`.

        A commit can be rejected while the consumer group rebalances or the
        broker is unreachable. Letting that escape would end the polling task and
        stop every subscription this consumer owns, so the rejection is logged
        and the next processed message commits a higher offset in its place.
        """
        try:
            committed = await self.consumer.commit(message=message, asynchronous=False)
        except KafkaException as error:
            logger.error(
                f"Offset commit failed for event type {message.topic()}: {error}"
            )
            return
        for position in committed:
            if position.error is not None:
                logger.error(
                    f"Offset commit rejected for {position.topic} "
                    f"[{position.partition}]: {position.error}"
                )

    async def _rewind_to(self, position: TopicPartition) -> None:
        """Move the consume position back so the next poll returns that message.

        Leaving the offset uncommitted is not enough on its own: the consumer's
        in-memory position has already moved past the message, so the next
        message that succeeds would commit an offset beyond the failed one and
        the failure would never come back.
        """
        try:
            await self.consumer.seek(position)
        except KafkaException as error:
            logger.error(
                f"Cannot rewind {position.topic} [{position.partition}] to offset "
                f"{position.offset}, message is not retryable: {error}"
            )

    async def _dispatch_to_handlers(
        self,
        message: Message,
        topic: str,
        event_type: type[AbstractEvent],
        headers: dict[str, str],
    ) -> MessageOutcome:
        """Run every handler registered for one polled message.

        Returns:
            `PROCESSED` when the consumer is done with the message, `RETRYABLE`
            when the message must be delivered again.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable, which is not a verdict about this message.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, which is not a verdict about this message.
        """
        event_message: bytes | None = message.value()
        if event_message is None:
            logger.warning(f"Received empty message for event type: {topic}")
            return MessageOutcome.PROCESSED
        try:
            event_data = self.type_adapters[event_type].validate_json(event_message)
        except ValidationError as error:
            # 역직렬화 실패는 같은 본문으로 재시도해도 결과가 같으므로 즉시 보낸다.
            logger.error(f"Cannot deserialize message from topic {topic}: {error}")
            return await self._dead_letter_outcome(topic, message, headers, error)
        remaining_retries = self.config.max_handler_retries
        while True:
            try:
                await self._invoke_handlers(event_type, event_data, headers)
                return MessageOutcome.PROCESSED
            except (
                AuthVerificationProviderUnavailableError,
                AuthRequirementProviderUnavailableError,
            ):
                raise
            except (AuthContextNotFoundError, AuthRequirementDeniedError) as error:
                logger.warning(
                    f"Auth boundary refused message for event type {topic}, "
                    f"discarding it: {error}"
                )
                return MessageOutcome.PROCESSED
            except Exception as error:
                if remaining_retries == 0:
                    logger.error(
                        f"Error processing message for event type {topic}: {error}"
                    )
                    return await self._dead_letter_outcome(
                        topic, message, headers, error
                    )
                remaining_retries -= 1
                logger.warning(
                    f"Retrying message for event type {topic} after error: {error}"
                )

    async def _route_event_handler(self, message: Message) -> None:
        if message.error():  # pragma: no cover - Kafka 브로커 에러 콜백
            logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        partition: int | None = message.partition()
        offset: int | None = message.offset()
        if (  # pragma: no cover - Kafka 메시지 비정상 상태
            topic is None or partition is None or offset is None
        ):
            logger.warning("Received message with no topic, partition or offset.")
            return
        event_type: type[AbstractEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover - 미등록 이벤트 타입 수신 방어
            logger.warning(f"Received message for unknown event type: {topic}")
            return
        headers = self._to_string_headers(message.headers())
        if self._propagator is not None:
            carrier = headers
            parent = self._propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        try:
            outcome = await self._dispatch_to_handlers(
                message, topic, event_type, headers
            )
            match outcome:
                case MessageOutcome.PROCESSED:
                    await self._commit_offset(message)
                case (
                    MessageOutcome.RETRYABLE
                ):  # pragma: no branch - 전수 분기, 미매치 불가
                    await self._rewind_to(TopicPartition(topic, partition, offset))
        finally:
            if self._propagator is not None:
                TraceContext.clear()

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None:
        """Register an async handler for the given event type."""
        if event not in self.handlers:
            self.handlers[event] = []
            self.type_adapters[event] = cast(
                TypeAdapter[AbstractEvent], TypeAdapter(event)
            )
            self.type_lookup[_event_routing_name(event)] = event
        self.handlers[event].append(handler)

    @override
    async def initialize_async(self) -> None:
        """Create Kafka topics, open the dead-letter producer, and subscribe."""
        self.consumer = AIOConsumer(self.config.consumer_configuration_dict)
        self.producer = AIOKafkaProducer(
            **self.config.async_producer_configuration_dict
        )
        await self.producer.start()
        topics: list[str] = [
            _event_routing_name(event_type) for event_type in self.handlers.keys()
        ]
        self._create_topics(
            topics=topics
            + [f"{topic}{self.config.dead_letter_topic_suffix}" for topic in topics]
        )
        await self.consumer.subscribe(topics=topics)

    @override
    async def run_async(self) -> None:  # pragma: no cover - 별도 asyncio 태스크로 실행
        """Poll Kafka asynchronously for messages and route them to handlers."""
        while not self._stop_event.is_set():
            message: Message | None = await self.consumer.poll(
                timeout=self.config.poll_timeout
            )
            if message is None:
                continue
            await self._route_event_handler(message)

    @override
    async def dispose_async(self) -> None:
        """Flush pending dead-letter records and close the async Kafka consumer."""
        await self.producer.stop()
        await self.consumer.close()
