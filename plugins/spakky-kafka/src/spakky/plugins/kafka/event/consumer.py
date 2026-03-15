from logging import getLogger
from typing import Any

from confluent_kafka import Consumer, Message
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.aio import AIOConsumer
from pydantic import TypeAdapter
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.domain.models.event import AbstractEvent
from spakky.event.error import (
    DuplicateEventHandlerError,
)
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    EventT_contra,
    IAsyncEventConsumer,
    IEventConsumer,
)

from spakky.plugins.kafka.common.config import KafkaConnectionConfig

logger = getLogger(__name__)


@Pod()
class KafkaEventConsumer(IEventConsumer, AbstractBackgroundService):
    """Synchronous Kafka event consumer that polls messages and dispatches to handlers."""

    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractEvent]]
    type_adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    handlers: dict[type[AbstractEvent], EventHandlerCallback[Any]]
    admin: AdminClient
    consumer: Consumer

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self.admin = AdminClient(self.config.configuration_dict)
        self.consumer = Consumer(
            self.config.configuration_dict,
            logger=logger,
        )

    def _create_topics(self, topics: list[str]) -> None:
        if not topics:  # pragma: no cover
            return
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:  # pragma: no cover
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

    def _route_event_handler(self, message: Message) -> None:
        if message.error():  # pragma: no cover
            logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        if topic is None:  # pragma: no cover
            logger.warning("Received message with no topic.")
            return
        event_type: type[AbstractEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover
            logger.warning(f"Received message for unknown event type: {topic}")
            return
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handler = self.handlers[event_type]
            handler(event_data)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error processing message for event type {topic}: {e}")

    def register(
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None:
        """Register a handler for the given event type."""
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)
        self.type_lookup[event.__name__] = event

    def initialize(self) -> None:
        """Create Kafka topics and subscribe the consumer."""
        topics: list[str] = [event_type.__name__ for event_type in self.handlers.keys()]
        self._create_topics(topics=topics)
        self.consumer.subscribe(topics=topics)

    def run(self) -> None:
        """Poll Kafka for messages and route them to registered handlers."""
        while not self._stop_event.is_set():
            message: Message | None = self.consumer.poll(
                timeout=self.config.poll_timeout
            )
            if message is None:
                continue
            self._route_event_handler(message)

    def dispose(self) -> None:
        """Close the Kafka consumer connection."""
        self.consumer.close()


@Pod()
class AsyncKafkaEventConsumer(IAsyncEventConsumer, AbstractAsyncBackgroundService):
    """Asynchronous Kafka event consumer that polls messages and dispatches to handlers."""

    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractEvent]]
    type_adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    handlers: dict[type[AbstractEvent], AsyncEventHandlerCallback[Any]]
    admin: AdminClient
    consumer: AIOConsumer

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self.admin = AdminClient(self.config.configuration_dict)

    def _create_topics(self, topics: list[str]) -> None:
        if not topics:  # pragma: no cover
            return
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        topics_to_create: set[str] = set(topics) - existing_topics
        if not topics_to_create:  # pragma: no cover
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

    async def _route_event_handler(  # pragma: no cover - 별도 asyncio 태스크로 실행
        self, message: Message
    ) -> None:
        if message.error():  # pragma: no cover
            logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        if topic is None:  # pragma: no cover
            logger.warning("Received message with no topic.")
            return
        event_type: type[AbstractEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover
            logger.warning(f"Received message for unknown event type: {topic}")
            return
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handler = self.handlers[event_type]
            await handler(event_data)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error processing message for event type {topic}: {e}")

    def register(
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None:
        """Register an async handler for the given event type."""
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)
        self.type_lookup[event.__name__] = event

    async def initialize_async(self) -> None:
        """Create Kafka topics and subscribe the async consumer."""
        self.consumer = AIOConsumer(self.config.configuration_dict)
        topics: list[str] = [event_type.__name__ for event_type in self.handlers.keys()]
        self._create_topics(topics=topics)
        await self.consumer.subscribe(topics=topics)

    async def run_async(self) -> None:  # pragma: no cover - 별도 asyncio 태스크로 실행
        """Poll Kafka asynchronously for messages and route them to handlers."""
        while not self._stop_event.is_set():
            message: Message | None = await self.consumer.poll(
                timeout=self.config.poll_timeout
            )
            if message is None:
                continue
            await self._route_event_handler(message)

    async def dispose_async(self) -> None:
        """Close the async Kafka consumer connection."""
        await self.consumer.close()
