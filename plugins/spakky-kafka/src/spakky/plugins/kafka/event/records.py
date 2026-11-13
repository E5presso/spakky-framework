"""Broker-neutral delivery state mapped onto Kafka records and headers.

Everything here is pure: it turns polled messages into typed records and
builds the headers of the records a subscriber publishes for a delayed retry,
a dead letter or a failed redrive. The clients that move those records live in
`spakky.plugins.kafka.event.worker`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from logging import getLogger
from typing import Self

from confluent_kafka import KafkaError, Message, TopicPartition
from pydantic import BaseModel, ConfigDict
from spakky.event.delivery import (
    DeadLetter,
    DeliveryDeadLettered,
    DeliveryDeferred,
    DeliveryHeader,
    DeliveryHeaders,
    DeliveryRetry,
    DeliveryState,
    HandlerFailure,
)
from spakky.event.error import (
    EventDeferredError,
    InvalidDeliveryHeaderError,
    InvalidMessageError,
)
from spakky.event.subscription import HandlerName, SubscriberName

from spakky.plugins.kafka.common.constants import (
    DeadLetterHeaderKey,
    KafkaGroupId,
    KafkaTopic,
)

logger = getLogger(__name__)

type RawKafkaHeaders = (
    dict[str, bytes | str | None] | list[tuple[str, bytes | str | None]] | None
)
"""Headers as the Kafka client hands them over: a mapping, pairs, or nothing."""

type EncodedKafkaHeaders = list[tuple[str, bytes]]
"""Headers in the byte-valued pair form the asynchronous producer accepts."""

type UnsettledOutcome = DeliveryRetry | DeliveryDeferred | DeliveryDeadLettered
"""A delivery outcome other than completion."""

type PartitionKey = tuple[KafkaTopic, int]
"""Topic and partition number identifying one partition of a subscriber."""

type RecordCoordinates = tuple[KafkaTopic, int, int]
"""Topic, partition number and offset identifying one consumed record."""


class ConsumedRecord(BaseModel):
    """One polled Kafka message with its coordinates known to be present."""

    model_config = ConfigDict(frozen=True)

    topic: KafkaTopic
    partition: int
    offset: int
    key: bytes | None
    """Partitioning key; None when the publisher set none."""

    value: bytes | None
    """Serialized event; None is a record without a body."""

    headers: dict[str, str]
    timestamp: int
    """Broker or producer timestamp of the record in milliseconds."""

    @classmethod
    def from_message(cls, message: Message) -> Self:
        """Read a polled message into a typed record.

        Raises:
            InvalidMessageError: The message carries no topic, partition or offset.
        """
        topic = message.topic()
        partition = message.partition()
        offset = message.offset()
        if topic is None or partition is None or offset is None:
            raise InvalidMessageError()
        _, timestamp = message.timestamp()
        return cls(
            topic=topic,
            partition=partition,
            offset=offset,
            key=message.key(),
            value=message.value(),
            headers=KafkaDeliveryHeaders.decode(message.headers()),
            timestamp=timestamp,
        )

    @property
    def partition_key(self) -> PartitionKey:
        """Partition the record was read from."""
        return (self.topic, self.partition)

    @property
    def coordinates(self) -> RecordCoordinates:
        """Identity of the record inside its subscriber."""
        return (self.topic, self.partition, self.offset)

    @property
    def position(self) -> TopicPartition:
        """Consume position that makes the next poll return this record again."""
        return TopicPartition(self.topic, self.partition, self.offset)

    @property
    def next_position(self) -> TopicPartition:
        """Offset to commit once the subscriber is done with this record."""
        return TopicPartition(self.topic, self.partition, self.offset + 1)


# dataclass: holds a confluent_kafka TopicPartition, which is not a pydantic type.
@dataclass(frozen=True, slots=True)
class PartitionFence:
    """A partition paused until a waiting record becomes due again."""

    position: TopicPartition
    """Record the partition is rewound to when the wait ends."""

    deadline: float
    """Monotonic time at which the partition is resumed."""


class KafkaDeliveryReport:
    """Broker verdict on one record handed to the synchronous producer.

    `Producer.produce` only enqueues, so a refusal the broker decides, such as
    a failed authorization or a delivery timeout, surfaces only in the
    delivery callback. The report keeps that verdict for the caller.
    """

    topic: KafkaTopic
    delivered: bool

    def __init__(self, topic: KafkaTopic) -> None:
        self.topic = topic
        self.delivered = False

    def on_delivery(self, error: KafkaError | None, message: Message) -> None:
        """Record whether the broker accepted the record."""
        if error is not None:
            logger.error(f"Delivery to {self.topic} failed: {error}")
            return
        self.delivered = True


class KafkaDeliveryHeaders:
    """Builds and reads the headers that carry delivery state on Kafka records."""

    @staticmethod
    def decode(raw: RawKafkaHeaders) -> dict[str, str]:
        """Convert Kafka message headers to a string-valued carrier dict.

        Kafka headers may be a list of (key, value) tuples or a dict. Values
        can be bytes, str, or None; bytes are decoded, str kept, None skipped.
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

    @staticmethod
    def encode(headers: DeliveryHeaders) -> EncodedKafkaHeaders:
        """Encode string headers into byte-valued pairs."""
        return [(key, value.encode()) for key, value in headers.items()]

    @staticmethod
    def origin(
        record: ConsumedRecord, origin_topic: KafkaTopic, carried: bool
    ) -> dict[str, str]:
        """Return the headers naming where the event was first consumed from.

        Args:
            record: Record the subscriber is settling.
            origin_topic: Event topic the record belongs to.
            carried: Whether the record is a copy (a waiting retry or a dead
                letter) that already carries its original coordinates.
        """
        observed = {
            DeadLetterHeaderKey.ORIGINAL_TOPIC.value: origin_topic,
            DeadLetterHeaderKey.ORIGINAL_PARTITION.value: str(record.partition),
            DeadLetterHeaderKey.ORIGINAL_OFFSET.value: str(record.offset),
            DeadLetterHeaderKey.ORIGINAL_TIMESTAMP.value: str(record.timestamp),
        }
        if not carried:
            return observed
        return {key: record.headers.get(key, value) for key, value in observed.items()}

    @staticmethod
    def retry(
        record: ConsumedRecord,
        origin_topic: KafkaTopic,
        carried: bool,
        state: DeliveryState,
        not_before: float,
    ) -> dict[str, str]:
        """Build the headers of a record set aside for a delayed retry.

        Args:
            record: Record whose delivery failed.
            origin_topic: Event topic the record belongs to.
            carried: Whether the record itself was read from the retry topic.
            state: Retry state the next attempt starts from.
            not_before: Wall-clock epoch seconds before which it must not run.
        """
        kept = {
            key: value
            for key, value in record.headers.items()
            if key not in DeliveryHeader
        }
        return {
            **kept,
            **KafkaDeliveryHeaders.origin(record, origin_topic, carried),
            **state.to_headers(),
            DeliveryHeader.NOT_BEFORE.value: repr(not_before),
        }

    @staticmethod
    def not_before(headers: DeliveryHeaders) -> float:
        """Read when a waiting retry becomes due, as wall-clock epoch seconds.

        A record without the header was not scheduled by a subscriber, so it is
        due at once.

        Raises:
            InvalidDeliveryHeaderError: The header is present but not a number.
        """
        value = headers.get(DeliveryHeader.NOT_BEFORE.value)
        if value is None:
            return 0.0
        try:
            return float(value)
        except ValueError as error:
            raise InvalidDeliveryHeaderError() from error

    @staticmethod
    def dead_letter(
        record: ConsumedRecord,
        origin_topic: KafkaTopic,
        carried: bool,
        group_id: KafkaGroupId,
        dead_letter: DeadLetter,
    ) -> dict[str, str]:
        """Build the headers of a dead-letter record.

        The original headers travel with the record, followed by its original
        coordinates, the group that gave up, and the broker-neutral metadata a
        redrive reads. The exception headers describe the first failed handler.
        """
        kept = {
            key: value
            for key, value in record.headers.items()
            if key not in DeliveryHeader
        }
        headers = {
            **kept,
            **KafkaDeliveryHeaders.origin(record, origin_topic, carried),
            DeadLetterHeaderKey.CONSUMER_GROUP.value: group_id,
            **dead_letter.to_headers(),
        }
        for failure in dead_letter.failures[:1]:
            headers[DeadLetterHeaderKey.EXCEPTION_TYPE.value] = failure.exception_type
            headers[DeadLetterHeaderKey.EXCEPTION_MESSAGE.value] = (
                failure.exception_message
            )
        return headers

    @staticmethod
    def redrive_pending(headers: DeliveryHeaders) -> frozenset[HandlerName] | None:
        """Return the handlers a redrive runs for one dead letter.

        A dead letter written before per-handler metadata existed names no
        handlers, so None is returned and every handler runs.
        """
        try:
            return DeadLetter.from_headers(headers).pending
        except InvalidDeliveryHeaderError:
            return None

    @staticmethod
    def previous_attempts(headers: DeliveryHeaders) -> int:
        """Return how many attempts a dead letter had used before a redrive."""
        try:
            return DeadLetter.from_headers(headers).attempts
        except InvalidDeliveryHeaderError:
            return 0


class KafkaDeadLetters:
    """Builds dead-letter verdicts the delivery contract does not settle itself."""

    @staticmethod
    def undeliverable(
        origin_topic: KafkaTopic,
        subscriber: SubscriberName | None,
        handlers: list[HandlerName],
        attempt: int,
        error: Exception,
    ) -> DeliveryDeadLettered:
        """Dead-letter a record no retry can turn into a handler call.

        Args:
            origin_topic: Event topic the record belongs to.
            subscriber: Subscriber giving up; None is the unnamed subscriber.
            handlers: Handlers that never received the event.
            attempt: 1-based number of the attempt that could not run.
            error: Why the record cannot be delivered.
        """
        return DeliveryDeadLettered(
            dead_letter=DeadLetter(
                event_name=origin_topic,
                subscriber=subscriber,
                failures=tuple(
                    HandlerFailure(
                        handler=handler,
                        exception_type=type(error).__qualname__,
                        exception_message=str(error),
                        retryable=False,
                    )
                    for handler in handlers
                ),
                attempts=attempt,
                failed_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def after_redrive(
        origin_topic: KafkaTopic,
        subscriber: SubscriberName | None,
        outcome: UnsettledOutcome,
        previous_attempts: int,
    ) -> DeadLetter:
        """Describe a dead letter that failed again when it was redriven.

        A redrive makes one attempt, so an outcome that would normally wait for
        another attempt is recorded as the new state of the dead letter.

        Args:
            origin_topic: Event topic the dead letter belongs to.
            subscriber: Subscriber owning the dead letter.
            outcome: What the redrive attempt settled.
            previous_attempts: Attempts recorded before this redrive.
        """
        match outcome:
            case DeliveryDeadLettered(dead_letter=dead_letter):
                failures = dead_letter.failures
            case DeliveryRetry(failures=retry_failures):
                failures = retry_failures
            case DeliveryDeferred(  # pragma: no branch - 전수 분기, 미매치 불가
                state=state
            ):
                failures = tuple(
                    HandlerFailure(
                        handler=handler,
                        exception_type=EventDeferredError.__qualname__,
                        exception_message=EventDeferredError.message,
                        retryable=True,
                    )
                    for handler in sorted(state.pending or ())
                )
        return DeadLetter(
            event_name=origin_topic,
            subscriber=subscriber,
            failures=failures,
            attempts=previous_attempts + 1,
            failed_at=datetime.now(UTC),
        )
