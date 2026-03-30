import asyncio
from logging import getLogger

from confluent_kafka import KafkaError, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from spakky.core.pod.annotations.pod import Pod
from spakky.event.event_publisher import (
    IAsyncEventTransport,
    IEventTransport,
)

from spakky.plugins.kafka.common.config import KafkaConnectionConfig

logger = getLogger(__name__)


@Pod()
class KafkaEventTransport(IEventTransport):
    """Synchronous Kafka event transport using confluent_kafka Producer."""

    config: KafkaConnectionConfig
    admin: AdminClient
    producer: Producer

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka producer with connection config."""
        self.config = config
        self.admin = AdminClient(self.config.configuration_dict)
        self.producer = Producer(self.config.configuration_dict, logger=logger)

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
        if error is not None:  # pragma: no cover
            logger.error(f"Message delivery failed: {error}")
        else:
            logger.info(
                f"Message delivered to {message.topic()} [{message.partition()}] at offset {message.offset()}"
            )

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Send a pre-serialized event payload to Kafka.

        Args:
            event_name: Topic name (typically the event class name).
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
        """
        self._create_topic(topic=event_name)
        self.producer.produce(
            topic=event_name,
            value=payload,
            headers=dict(headers),
            callback=self._message_delivery_report,
        )
        self.producer.poll(0)
        self.producer.flush()


@Pod()
class AsyncKafkaEventTransport(IAsyncEventTransport):
    """Asynchronous Kafka event transport using confluent_kafka Producer."""

    config: KafkaConnectionConfig
    admin: AdminClient

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka transport with connection config."""
        self.config = config
        self.admin = AdminClient(self.config.configuration_dict)

    def _create_topic(  # pragma: no cover - Kafka 브로커 콜백으로 커버리지 수집 불가
        self, topic: str
    ) -> None:
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

    def _message_delivery_report(  # pragma: no cover - Kafka 프로듀서 콜백으로 실행
        self,
        error: KafkaError | None,
        message: Message,
    ) -> None:
        if error is not None:
            logger.error(f"Message delivery failed: {error}")
        else:
            logger.info(
                f"Message delivered to {message.topic()} [{message.partition()}] at offset {message.offset()}"
            )

    def _send_sync(
        self, event_name: str, payload: bytes, headers: dict[str, str]
    ) -> None:
        producer = Producer(self.config.configuration_dict, logger=logger)
        self._create_topic(topic=event_name)
        producer.produce(
            topic=event_name,
            value=payload,
            headers=dict(headers),
            callback=self._message_delivery_report,
        )
        producer.poll(0)
        producer.flush()

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Asynchronously send a pre-serialized event payload to Kafka.

        Args:
            event_name: Topic name (typically the event class name).
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_sync, event_name, payload, headers)
