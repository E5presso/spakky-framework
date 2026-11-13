"""Kafka integration event consumers.

The consumers implement the broker-neutral delivery contract of
`spakky.event.delivery`. Every subscriber is served by its own worker (see
`spakky.plugins.kafka.event.worker`), so each one reads through its own
consumer group and keeps its own retries and dead-letter topic.
"""

from asyncio import Lock as AsyncLock
from asyncio import create_task, gather, to_thread
from logging import getLogger
from threading import Lock, Thread
from typing import Any, override

from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.domain.models.event import AbstractEvent, AbstractIntegrationEvent
from spakky.event.delivery import (
    AsyncEventSubscriptions,
    EventRouting,
    EventSubscriptions,
)
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.redrive import IAsyncEventRedriver, IEventRedriver, RedriveResult
from spakky.event.subscription import HandlerName, SubscriberName
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.common.constants import KafkaTopic
from spakky.plugins.kafka.event.worker import (
    AsyncKafkaSubscriberWorker,
    KafkaSubscriberWorker,
)

logger = getLogger(__name__)


@Pod()
class KafkaEventConsumer(
    IIntegrationEventConsumer, IEventRedriver, AbstractBackgroundService
):
    """Synchronous Kafka consumer that runs one worker thread per subscriber."""

    config: KafkaConnectionConfig
    admin: AdminClient
    subscriptions: EventSubscriptions
    workers: dict[SubscriberName | None, KafkaSubscriberWorker]
    """Worker of every subscriber with a registered handler; None is unnamed."""

    _propagator: ITracePropagator | None
    # Any: handlers are registered per concrete event type.
    _auth_boundary_handlers: set[EventHandlerCallback[Any]]
    _redrive_lock: Lock

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.subscriptions = EventSubscriptions(config.retry)
        self.workers = {}
        self._propagator = None
        self._auth_boundary_handlers = set()
        self._redrive_lock = Lock()
        self.admin = AdminClient(self.config.connection_configuration_dict)

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator
        for worker in self.workers.values():
            worker.propagator = propagator

    def register_auth_boundary(self, handler: EventHandlerCallback[Any]) -> None:
        """Mark a registered post-processor endpoint as Kafka auth-aware."""
        self._auth_boundary_handlers.add(handler)

    def _create_topics(self, topics: list[KafkaTopic]) -> None:
        """Create the topics that do not exist yet and wait for the broker.

        A topic created concurrently by another consumer is not a failure.
        """
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:
            return
        futures = self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
                for topic in topics_to_create
            ]
        )
        for topic, future in futures.items():
            try:
                future.result(self.config.dead_letter_delivery_timeout)
            except KafkaException as error:
                if error.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
                logger.info(f"Topic {topic} was created concurrently")

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register a handler in the subscription of `subscriber` for `event`."""
        delivery = self.subscriptions.register(event, handler, subscriber, handler_name)
        worker = self.workers.get(delivery.subscriber)
        if worker is None:
            worker = KafkaSubscriberWorker(
                self.config, delivery.subscriber, self._auth_boundary_handlers
            )
            worker.propagator = self._propagator
            self.workers[delivery.subscriber] = worker
        worker.add(delivery)

    @override
    def initialize(self) -> None:
        """Create every subscriber's topics and open every subscriber's clients."""
        if not self.workers:
            return
        self._create_topics(
            [
                topic
                for worker in self.workers.values()
                for topic in worker.managed_topics
            ]
        )
        for worker in self.workers.values():
            worker.open()

    @override
    def run(self) -> None:
        """Run every subscriber's poll loop on its own thread until stopped.

        A subscriber whose loop ends with an error leaves the others running.
        """
        threads = [
            Thread(
                target=worker.run,
                args=(self._stop_event,),
                daemon=True,
                name=f"{type(self).__name__}[{worker.group_id}]",
            )
            for worker in self.workers.values()
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    @override
    def dispose(self) -> None:
        """Flush pending records and close every subscriber's clients."""
        for worker in self.workers.values():
            worker.close()

    @override
    def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Deliver dead letters of `subscriber` for `event` to their failed handlers.

        Redrives of this consumer run one at a time, so two calls never read
        the same dead letters.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self.subscriptions.get(subscriber, event)
        with self._redrive_lock:
            return self.workers[delivery.subscriber].redrive(
                EventRouting.name_of(event), limit
            )


@Pod()
class AsyncKafkaEventConsumer(
    IAsyncIntegrationEventConsumer, IAsyncEventRedriver, AbstractAsyncBackgroundService
):
    """Asynchronous Kafka consumer that runs one worker task per subscriber."""

    config: KafkaConnectionConfig
    admin: AdminClient
    subscriptions: AsyncEventSubscriptions
    workers: dict[SubscriberName | None, AsyncKafkaSubscriberWorker]
    """Worker of every subscriber with a registered handler; None is unnamed."""

    _propagator: ITracePropagator | None
    # Any: handlers are registered per concrete event type.
    _auth_boundary_handlers: set[AsyncEventHandlerCallback[Any]]
    _redrive_lock: AsyncLock

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.subscriptions = AsyncEventSubscriptions(config.retry)
        self.workers = {}
        self._propagator = None
        self._auth_boundary_handlers = set()
        self._redrive_lock = AsyncLock()
        self.admin = AdminClient(self.config.connection_configuration_dict)

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator
        for worker in self.workers.values():
            worker.propagator = propagator

    def register_auth_boundary(self, handler: AsyncEventHandlerCallback[Any]) -> None:
        """Mark a registered post-processor endpoint as Kafka auth-aware."""
        self._auth_boundary_handlers.add(handler)

    def _create_topics(self, topics: list[KafkaTopic]) -> None:
        """Create the topics that do not exist yet and wait for the broker.

        A topic created concurrently by another consumer is not a failure.
        """
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:
            return
        futures = self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
                for topic in topics_to_create
            ]
        )
        for topic, future in futures.items():
            try:
                future.result(self.config.dead_letter_delivery_timeout)
            except KafkaException as error:
                if error.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
                logger.info(f"Topic {topic} was created concurrently")

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register an async handler in the subscription of `subscriber` for `event`."""
        delivery = self.subscriptions.register(event, handler, subscriber, handler_name)
        worker = self.workers.get(delivery.subscriber)
        if worker is None:
            worker = AsyncKafkaSubscriberWorker(
                self.config, delivery.subscriber, self._auth_boundary_handlers
            )
            worker.propagator = self._propagator
            self.workers[delivery.subscriber] = worker
        worker.add(delivery)

    @override
    async def initialize_async(self) -> None:
        """Create every subscriber's topics and open every subscriber's clients."""
        if not self.workers:
            return
        await to_thread(
            self._create_topics,
            [
                topic
                for worker in self.workers.values()
                for topic in worker.managed_topics
            ],
        )
        for worker in self.workers.values():
            await worker.open()

    @override
    async def run_async(self) -> None:
        """Run every subscriber's poll loop as its own task until stopped.

        A subscriber whose loop ends with an error leaves the others running;
        the first such error is raised once every loop has ended.
        """
        results = await gather(
            *(
                create_task(
                    worker.run(self._stop_event),
                    name=f"{type(self).__name__}[{worker.group_id}]",
                )
                for worker in self.workers.values()
            ),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    @override
    async def dispose_async(self) -> None:
        """Flush pending records and close every subscriber's clients."""
        for worker in self.workers.values():
            await worker.close()

    @override
    async def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Deliver dead letters of `subscriber` for `event` to their failed handlers.

        Redrives of this consumer run one at a time, so two calls never read
        the same dead letters.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self.subscriptions.get(subscriber, event)
        async with self._redrive_lock:
            return await self.workers[delivery.subscriber].redrive(
                EventRouting.name_of(event), limit
            )
