"""Shared fakes that drive the sync and async subscriber workers the same way.

Both workers implement one contract, so every scenario is written once and run
against each of them through a harness that hides `await` and the two producer
client shapes.
"""

import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka import KafkaError, KafkaException, TopicPartition
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.delivery import AsyncSubscriptionDelivery, SubscriptionDelivery
from spakky.event.redrive import RedriveResult
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.worker import (
    AsyncKafkaSubscriberWorker,
    KafkaSubscriberWorker,
)

WORKER_MODULE = "spakky.plugins.kafka.event.worker"
SAMPLE_TIMESTAMP = (1, 1700000000000)
"""Kafka `(timestamp_type, timestamp)` pair returned by `Message.timestamp()`."""

SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"
SAMPLE_PAYLOAD = b'{"data": "hello"}'

type SyncHandler = Callable[..., None]
"""Handler body written once; the async harness wraps it in a coroutine."""


@immutable
class SampleEvent(AbstractIntegrationEvent):
    """Test integration event."""

    data: str


@immutable
class AnotherEvent(AbstractIntegrationEvent):
    """Another test integration event."""

    value: int


@immutable
class RenamedEvent(AbstractIntegrationEvent):
    """Integration event with custom outbound topic identity."""

    data: str

    @property
    @override
    def event_name(self) -> str:
        return "external.renamed.v1"


class Clock:
    """Controllable replacement for the monotonic and wall clocks of the worker."""

    now: float
    step: float
    """Seconds every monotonic reading advances the clock by."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.step = 0.0

    def monotonic(self) -> float:
        self.now += self.step
        return self.now

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_message(
    topic: str = "SampleEvent",
    partition: int = 3,
    offset: int = 42,
    value: bytes | None = SAMPLE_PAYLOAD,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a polled Kafka message stub with real coordinates."""
    message = MagicMock()
    message.error.return_value = None
    message.topic.return_value = topic
    message.partition.return_value = partition
    message.offset.return_value = offset
    message.timestamp.return_value = SAMPLE_TIMESTAMP
    message.key.return_value = b"order-1"
    message.value.return_value = value
    message.headers.return_value = [
        (key, item.encode()) for key, item in (headers or {}).items()
    ]
    return message


@dataclass(frozen=True, slots=True)
class Published:
    """One record a worker copied to a retry or dead-letter topic."""

    topic: str
    value: bytes | None
    key: bytes | None
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class RedriveRun:
    """What one redrive call did against its dedicated clients."""

    result: RedriveResult
    consumer: MagicMock
    consumer_config: dict[str, Any]
    published: list[Published]


def position_of(call: Any) -> tuple[str, int, int]:
    """Read topic, partition and offset of a TopicPartition passed to a client."""
    argument = call.args[0] if call.args else call.kwargs["offsets"]
    position: TopicPartition = argument[0] if isinstance(argument, list) else argument
    return (position.topic, position.partition, position.offset)


class AbstractWorkerHarness(ABC):
    """Drives one worker of either kind with plain synchronous calls."""

    config: KafkaConnectionConfig
    subscriber: str | None
    consumer: MagicMock
    producer: MagicMock
    auth_boundary_handlers: set[Any]
    redrive_consumer: MagicMock
    """Dedicated consumer of the last redrive, kept even when the call raised."""

    @abstractmethod
    def add(
        self,
        name: str,
        handler: SyncHandler,
        event: type[AbstractIntegrationEvent] = SampleEvent,
        auth_boundary: bool = False,
    ) -> None:
        """Register a handler body under a handler name."""
        ...

    @abstractmethod
    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Give the worker a trace propagator."""
        ...

    @abstractmethod
    def handle(self, message: MagicMock) -> None:
        """Deliver one polled message through the worker."""
        ...

    @abstractmethod
    def resume_due(self) -> None:
        """Let the worker resume partitions whose wait ended."""
        ...

    @abstractmethod
    def forget(self, partitions: list[TopicPartition]) -> None:
        """Fire the rebalance callback for some partitions."""
        ...

    @abstractmethod
    def run(self, polled: list[MagicMock | None]) -> None:
        """Run the poll loop over the given poll results, then stop it."""
        ...

    @abstractmethod
    def open(self) -> tuple[MagicMock, MagicMock]:
        """Open the worker against patched client classes and return them."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the worker's clients."""
        ...

    @abstractmethod
    def published(self) -> list[Published]:
        """Records the worker copied to retry or dead-letter topics."""
        ...

    @abstractmethod
    def refuse_publish(self) -> None:
        """Make the broker refuse every copied record."""
        ...

    @abstractmethod
    def redrive(
        self,
        messages: list[MagicMock | None],
        *,
        limit: int | None = None,
        committed: int = -1001,
        low: int = 0,
        high: int = 0,
        topic_known: bool = True,
        refuse_publish: bool = False,
        origin: str = "SampleEvent",
    ) -> RedriveRun:
        """Redrive against patched dedicated clients fed with `messages`."""
        ...

    @property
    @abstractmethod
    def worker_topics(self) -> tuple[list[str], list[str]]:
        """Subscribed and managed topics of the worker."""
        ...

    def committed(self) -> list[tuple[str, int, int]]:
        """Offsets the worker committed, in order."""
        return [position_of(call) for call in self.consumer.commit.call_args_list]

    def paused(self) -> list[tuple[str, int, int]]:
        """Positions the worker paused, in order."""
        return [position_of(call) for call in self.consumer.pause.call_args_list]

    def sought(self) -> list[tuple[str, int, int]]:
        """Positions the worker rewound to, in order."""
        return [position_of(call) for call in self.consumer.seek.call_args_list]

    def resumed(self) -> list[tuple[str, int, int]]:
        """Positions the worker resumed, in order."""
        return [position_of(call) for call in self.consumer.resume.call_args_list]


class SyncWorkerHarness(AbstractWorkerHarness):
    """Harness of `KafkaSubscriberWorker`."""

    worker: KafkaSubscriberWorker
    deliveries: dict[type[AbstractIntegrationEvent], SubscriptionDelivery]

    def __init__(self, config: KafkaConnectionConfig, subscriber: str | None) -> None:
        self.config = config
        self.subscriber = subscriber
        self.auth_boundary_handlers = set()
        self.worker = KafkaSubscriberWorker(
            config, subscriber, self.auth_boundary_handlers
        )
        self.deliveries = {}
        self.consumer = MagicMock()
        self.consumer.commit.return_value = []
        self.producer = self._delivering_producer()
        self.worker.consumer = self.consumer
        self.worker.producer = self.producer

    @staticmethod
    def _delivering_producer() -> MagicMock:
        producer = MagicMock()

        def produce(**kwargs: Any) -> None:
            kwargs["callback"](None, MagicMock())

        producer.produce.side_effect = produce
        producer.flush.return_value = 0
        return producer

    @staticmethod
    def _published(producer: MagicMock) -> list[Published]:
        return [
            Published(
                topic=call.kwargs["topic"],
                value=call.kwargs["value"],
                key=call.kwargs["key"],
                headers=dict(call.kwargs["headers"]),
            )
            for call in producer.produce.call_args_list
        ]

    @override
    def add(
        self,
        name: str,
        handler: SyncHandler,
        event: type[AbstractIntegrationEvent] = SampleEvent,
        auth_boundary: bool = False,
    ) -> None:
        if event not in self.deliveries:
            self.deliveries[event] = SubscriptionDelivery(
                event, self.subscriber, self.config.retry
            )
        self.deliveries[event].add(name, handler)
        self.worker.add(self.deliveries[event])
        if auth_boundary:
            self.auth_boundary_handlers.add(handler)

    @override
    def set_propagator(self, propagator: ITracePropagator) -> None:
        self.worker.propagator = propagator

    @override
    def handle(self, message: MagicMock) -> None:
        self.worker._handle(message)

    @override
    def resume_due(self) -> None:
        self.worker._resume_due()

    @override
    def forget(self, partitions: list[TopicPartition]) -> None:
        self.worker._forget(self.consumer, partitions)

    @override
    def run(self, polled: list[MagicMock | None]) -> None:
        stop_event = threading.Event()
        queue = list(polled)

        def poll(timeout: float) -> MagicMock | None:
            result = queue.pop(0)
            if not queue:
                stop_event.set()
            return result

        self.consumer.poll.side_effect = poll
        self.worker.run(stop_event)

    @override
    def open(self) -> tuple[MagicMock, MagicMock]:
        with (
            patch(f"{WORKER_MODULE}.Consumer") as consumer_cls,
            patch(f"{WORKER_MODULE}.Producer") as producer_cls,
        ):
            self.worker.open()
        return consumer_cls, producer_cls

    @override
    def close(self) -> None:
        self.worker.close()

    @override
    def published(self) -> list[Published]:
        return self._published(self.producer)

    @override
    def refuse_publish(self) -> None:
        self.producer.produce.side_effect = KafkaException(
            KafkaError(KafkaError.MSG_SIZE_TOO_LARGE)
        )

    @override
    def redrive(
        self,
        messages: list[MagicMock | None],
        *,
        limit: int | None = None,
        committed: int = -1001,
        low: int = 0,
        high: int = 0,
        topic_known: bool = True,
        refuse_publish: bool = False,
        origin: str = "SampleEvent",
    ) -> RedriveRun:
        topic = self.config.dead_letter_topic(origin, self.subscriber)
        consumer = MagicMock()
        consumer.commit.return_value = []
        metadata = MagicMock()
        metadata.topics = {topic: MagicMock(partitions={0: MagicMock()})}
        if not topic_known:
            metadata.topics = {}
        consumer.list_topics.return_value = metadata
        consumer.committed.return_value = [TopicPartition(topic, 0, committed)]
        consumer.get_watermark_offsets.return_value = (low, high)
        queue = list(messages)
        consumer.poll.side_effect = lambda timeout: queue.pop(0) if queue else None
        producer = self._delivering_producer()
        if refuse_publish:
            producer.produce.side_effect = KafkaException(
                KafkaError(KafkaError.MSG_SIZE_TOO_LARGE)
            )
        with (
            patch(f"{WORKER_MODULE}.Consumer", return_value=consumer) as consumer_cls,
            patch(f"{WORKER_MODULE}.Producer", return_value=producer),
        ):
            try:
                result = self.worker.redrive(origin, limit)
            finally:
                self.redrive_consumer = consumer
        return RedriveRun(
            result=result,
            consumer=consumer,
            consumer_config=consumer_cls.call_args.args[0],
            published=self._published(producer),
        )

    @property
    @override
    def worker_topics(self) -> tuple[list[str], list[str]]:
        return (self.worker.subscribed_topics, self.worker.managed_topics)


class AsyncWorkerHarness(AbstractWorkerHarness):
    """Harness of `AsyncKafkaSubscriberWorker`."""

    worker: AsyncKafkaSubscriberWorker
    deliveries: dict[type[AbstractIntegrationEvent], AsyncSubscriptionDelivery]

    def __init__(self, config: KafkaConnectionConfig, subscriber: str | None) -> None:
        self.config = config
        self.subscriber = subscriber
        self.auth_boundary_handlers = set()
        self.worker = AsyncKafkaSubscriberWorker(
            config, subscriber, self.auth_boundary_handlers
        )
        self.deliveries = {}
        self.consumer = AsyncMock()
        self.consumer.commit.return_value = []
        self.producer = AsyncMock()
        self.worker.consumer = self.consumer
        self.worker.producer = self.producer

    @staticmethod
    def _published(producer: MagicMock) -> list[Published]:
        return [
            Published(
                topic=call.kwargs["topic"],
                value=call.kwargs["value"],
                key=call.kwargs["key"],
                headers={key: value.decode() for key, value in call.kwargs["headers"]},
            )
            for call in producer.send_and_wait.call_args_list
        ]

    @override
    def add(
        self,
        name: str,
        handler: SyncHandler,
        event: type[AbstractIntegrationEvent] = SampleEvent,
        auth_boundary: bool = False,
    ) -> None:
        async def async_handler(*args: Any, **kwargs: Any) -> None:
            handler(*args, **kwargs)

        if event not in self.deliveries:
            self.deliveries[event] = AsyncSubscriptionDelivery(
                event, self.subscriber, self.config.retry
            )
        self.deliveries[event].add(name, async_handler)
        self.worker.add(self.deliveries[event])
        if auth_boundary:
            self.auth_boundary_handlers.add(async_handler)

    @override
    def set_propagator(self, propagator: ITracePropagator) -> None:
        self.worker.propagator = propagator

    @override
    def handle(self, message: MagicMock) -> None:
        asyncio.run(self.worker._handle(message))

    @override
    def resume_due(self) -> None:
        asyncio.run(self.worker._resume_due())

    @override
    def forget(self, partitions: list[TopicPartition]) -> None:
        asyncio.run(self.worker._forget(self.consumer, partitions))

    @override
    def run(self, polled: list[MagicMock | None]) -> None:
        queue = list(polled)

        async def scenario() -> None:
            stop_event = asyncio.Event()

            def poll(timeout: float) -> MagicMock | None:
                result = queue.pop(0)
                if not queue:
                    stop_event.set()
                return result

            self.consumer.poll.side_effect = poll
            await self.worker.run(stop_event)

        asyncio.run(scenario())

    @override
    def open(self) -> tuple[MagicMock, MagicMock]:
        with (
            patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls,
            patch(f"{WORKER_MODULE}.AIOKafkaProducer") as producer_cls,
        ):
            consumer_cls.return_value = AsyncMock()
            producer_cls.return_value = AsyncMock()
            asyncio.run(self.worker.open())
        return consumer_cls, producer_cls

    @override
    def close(self) -> None:
        asyncio.run(self.worker.close())

    @override
    def published(self) -> list[Published]:
        return self._published(self.producer)

    @override
    def refuse_publish(self) -> None:
        self.producer.send_and_wait.side_effect = KafkaException(
            KafkaError(KafkaError.MSG_SIZE_TOO_LARGE)
        )

    @override
    def redrive(
        self,
        messages: list[MagicMock | None],
        *,
        limit: int | None = None,
        committed: int = -1001,
        low: int = 0,
        high: int = 0,
        topic_known: bool = True,
        refuse_publish: bool = False,
        origin: str = "SampleEvent",
    ) -> RedriveRun:
        topic = self.config.dead_letter_topic(origin, self.subscriber)
        consumer = AsyncMock()
        consumer.commit.return_value = []
        metadata = MagicMock()
        metadata.topics = {topic: MagicMock(partitions={0: MagicMock()})}
        if not topic_known:
            metadata.topics = {}
        consumer.list_topics.return_value = metadata
        consumer.committed.return_value = [TopicPartition(topic, 0, committed)]
        consumer.get_watermark_offsets.return_value = (low, high)
        queue = list(messages)
        consumer.poll.side_effect = lambda timeout: queue.pop(0) if queue else None
        producer = AsyncMock()
        if refuse_publish:
            producer.send_and_wait.side_effect = KafkaException(
                KafkaError(KafkaError.MSG_SIZE_TOO_LARGE)
            )
        with (
            patch(
                f"{WORKER_MODULE}.AIOConsumer", return_value=consumer
            ) as consumer_cls,
            patch(f"{WORKER_MODULE}.AIOKafkaProducer", return_value=producer),
        ):
            try:
                result = asyncio.run(self.worker.redrive(origin, limit))
            finally:
                self.redrive_consumer = consumer
        producer.start.assert_awaited_once()
        producer.stop.assert_awaited_once()
        return RedriveRun(
            result=result,
            consumer=consumer,
            consumer_config=consumer_cls.call_args.args[0],
            published=self._published(producer),
        )

    @property
    @override
    def worker_topics(self) -> tuple[list[str], list[str]]:
        return (self.worker.subscribed_topics, self.worker.managed_topics)
