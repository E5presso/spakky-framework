from logging import Logger
from typing import Any

from confluent_kafka import Consumer, Message
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.experimental.aio import AIOConsumer
from pydantic import TypeAdapter
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.error import (
    DuplicateEventHandlerError,
)
from spakky.domain.ports.event.event_consumer import (
    DomainEventT,
    IAsyncEventConsumer,
    IAsyncEventHandlerCallback,
    IEventConsumer,
    IEventHandlerCallback,
)
from spakky.pod.annotations.pod import Pod
from spakky.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)

from spakky_kafka.common.config import KafkaConnectionConfig


@Pod()
class KafkaEventConsumer(IEventConsumer, AbstractBackgroundService):
    logger: Logger
    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractDomainEvent]]
    type_adapters: dict[type[AbstractDomainEvent], TypeAdapter[AbstractDomainEvent]]
    handlers: dict[type[AbstractDomainEvent], IEventHandlerCallback[Any]]
    admin: AdminClient
    consumer: Consumer

    def __init__(self, logger: Logger, config: KafkaConnectionConfig) -> None:
        super().__init__()
        self.logger = logger
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self.admin = AdminClient(self.config.configuration_dict)
        self.consumer = Consumer(
            self.config.configuration_dict,
            logger=self.logger,
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
            self.logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        if topic is None:  # pragma: no cover
            self.logger.warning("Received message with no topic.")
            return
        event_type: type[AbstractDomainEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover
            self.logger.warning(f"Received message for unknown event type: {topic}")
            return
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                self.logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handler = self.handlers[event_type]
            handler(event_data)
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Error processing message for event type {topic}: {e}")

    def register(
        self,
        event: type[DomainEventT],
        handler: IEventHandlerCallback[DomainEventT],
    ) -> None:
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)
        self.type_lookup[event.__name__] = event

    def initialize(self) -> None:
        topics: list[str] = [event_type.__name__ for event_type in self.handlers.keys()]
        self._create_topics(topics=topics)
        self.consumer.subscribe(topics=topics)

    def run(self) -> None:
        while not self._stop_event.is_set():
            message: Message | None = self.consumer.poll(timeout=1.0)
            if message is None:
                continue
            self._route_event_handler(message)

    def dispose(self) -> None:
        self.consumer.close()


@Pod()
class AsyncKafkaEventConsumer(IAsyncEventConsumer, AbstractAsyncBackgroundService):
    logger: Logger
    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractDomainEvent]]
    type_adapters: dict[type[AbstractDomainEvent], TypeAdapter[AbstractDomainEvent]]
    handlers: dict[type[AbstractDomainEvent], IAsyncEventHandlerCallback[Any]]
    admin: AdminClient
    consumer: AIOConsumer

    def __init__(self, logger: Logger, config: KafkaConnectionConfig) -> None:
        super().__init__()
        self.logger = logger
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

    async def _route_event_handler(self, message: Message) -> None:
        if message.error():  # pragma: no cover
            self.logger.error(f"Consumer error: {message.error()}")
            return
        topic: str | None = message.topic()
        if topic is None:  # pragma: no cover
            self.logger.warning("Received message with no topic.")
            return
        event_type: type[AbstractDomainEvent] | None = self.type_lookup.get(topic)
        if event_type is None:  # pragma: no cover
            self.logger.warning(f"Received message for unknown event type: {topic}")
            return
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                self.logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handler = self.handlers[event_type]
            await handler(event_data)
        except Exception as e:  # pragma: no cover
            self.logger.error(f"Error processing message for event type {topic}: {e}")

    def register(
        self,
        event: type[DomainEventT],
        handler: IAsyncEventHandlerCallback[DomainEventT],
    ) -> None:
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)
        self.type_lookup[event.__name__] = event

    async def initialize_async(self) -> None:
        self.consumer = AIOConsumer(self.config.configuration_dict)
        topics: list[str] = [event_type.__name__ for event_type in self.handlers.keys()]
        self._create_topics(topics=topics)
        await self.consumer.subscribe(topics=topics)

    async def run_async(self) -> None:
        while not self._stop_event.is_set():
            message: Message | None = await self.consumer.poll(timeout=1.0)
            if message is None:
                continue
            await self._route_event_handler(message)

    async def dispose_async(self) -> None:
        await self.consumer.close()
