from logging import Logger

from confluent_kafka import KafkaError, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.experimental.aio import AIOProducer
from pydantic import TypeAdapter
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)
from spakky.pod.annotations.pod import Pod

from spakky_kafka.common.config import KafkaConnectionConfig


@Pod()
class KafkaEventPublisher(IEventPublisher):
    logger: Logger
    config: KafkaConnectionConfig
    type_adapters: dict[type[AbstractDomainEvent], TypeAdapter[AbstractDomainEvent]]
    admin: AdminClient
    producer: Producer

    def __init__(self, logger: Logger, config: KafkaConnectionConfig) -> None:
        self.logger = logger
        self.config = config
        self.type_adapters = {}
        self.admin = AdminClient(self.config.configuration_dict)
        self.producer = Producer(self.config.configuration_dict, logger=self.logger)

    def _create_topic(self, topic: str) -> None:
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        if topic in existing_topics:
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
            ]
        )

    def _message_delivery_report(
        self,
        error: KafkaError | None,
        message: Message,
    ) -> None:
        if error is not None:
            self.logger.error(f"Message delivery failed: {error}")
        else:
            self.logger.info(
                f"Message delivered to {message.topic()} [{message.partition()}] at offset {message.offset()}"
            )

    def publish(self, event: AbstractDomainEvent) -> None:
        """Publish a domain event to Kafka.

        Args:
            event: The domain event to publish.
        """
        event_type = type(event)
        if event_type not in self.type_adapters:
            self.type_adapters[event_type] = TypeAdapter(event_type)
        self._create_topic(topic=event.event_name)
        self.producer.produce(
            topic=event.event_name,
            value=self.type_adapters[event_type].dump_json(event),
            callback=self._message_delivery_report,
        )
        self.producer.poll(0)
        self.producer.flush()


@Pod()
class AsyncKafkaEventPublisher(IAsyncEventPublisher):
    logger: Logger
    config: KafkaConnectionConfig
    type_adapters: dict[type[AbstractDomainEvent], TypeAdapter[AbstractDomainEvent]]
    admin: AdminClient
    producer: AIOProducer

    def __init__(self, logger: Logger, config: KafkaConnectionConfig) -> None:
        self.logger = logger
        self.config = config
        self.type_adapters = {}
        self.admin = AdminClient(self.config.configuration_dict)

    def _create_topic(self, topic: str) -> None:
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        if topic in existing_topics:
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
            ]
        )

    def _message_delivery_report(
        self,
        error: KafkaError | None,
        message: Message,
    ) -> None:
        if error is not None:
            self.logger.error(f"Message delivery failed: {error}")
        else:
            self.logger.info(
                f"Message delivered to {message.topic()} [{message.partition()}] at offset {message.offset()}"
            )

    async def publish(self, event: AbstractDomainEvent) -> None:
        """Asynchronously publish a domain event to Kafka.

        Args:
            event: The domain event to publish.
        """
        self.producer = AIOProducer(self.config.configuration_dict)
        event_type = type(event)
        if event_type not in self.type_adapters:
            self.type_adapters[event_type] = TypeAdapter(event_type)
        self._create_topic(topic=event.event_name)
        await self.producer.produce(
            topic=event.event_name,
            value=self.type_adapters[event_type].dump_json(event),
            callback=self._message_delivery_report,
        )
        await self.producer.poll(0)
        await self.producer.flush()
