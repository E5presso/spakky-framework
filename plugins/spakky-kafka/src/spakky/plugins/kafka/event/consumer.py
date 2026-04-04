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
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    EventT_contra,
    IAsyncEventConsumer,
    IEventConsumer,
)

from spakky.plugins.kafka.common.config import KafkaConnectionConfig

try:
    from spakky.tracing.context import TraceContext
    from spakky.tracing.propagator import ITracePropagator

    _HAS_TRACING = True
except ImportError:  # pragma: no cover - optional dependency (spakky-tracing)
    _HAS_TRACING = False

logger = getLogger(__name__)


@Pod()
class KafkaEventConsumer(IEventConsumer, AbstractBackgroundService):
    """Synchronous Kafka event consumer that polls messages and dispatches to handlers."""

    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractEvent]]
    type_adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    handlers: dict[type[AbstractEvent], list[EventHandlerCallback[Any]]]
    admin: AdminClient
    consumer: Consumer
    _propagator: object | None

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self._propagator = None
        self.admin = AdminClient(self.config.configuration_dict)
        self.consumer = Consumer(
            self.config.configuration_dict,
            logger=logger,
        )

    def set_propagator(self, propagator: object) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator

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
        if _HAS_TRACING and self._propagator is not None:
            propagator: ITracePropagator = self._propagator  # type: ignore[assignment]  # guarded by _HAS_TRACING
            carrier = self._to_string_headers(message.headers())
            parent = propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handlers = self.handlers[event_type]
            for handler in handlers:
                handler(event_data)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error processing message for event type {topic}: {e}")
        finally:
            if _HAS_TRACING and self._propagator is not None:
                TraceContext.clear()

    def register(
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None:
        """Register a handler for the given event type."""
        if event not in self.handlers:
            self.handlers[event] = []
            self.type_adapters[event] = TypeAdapter(event)
            self.type_lookup[event.__name__] = event
        self.handlers[event].append(handler)

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
    handlers: dict[type[AbstractEvent], list[AsyncEventHandlerCallback[Any]]]
    admin: AdminClient
    consumer: AIOConsumer
    _propagator: object | None

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka consumer with connection config."""
        super().__init__()
        self.config = config
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}
        self._propagator = None
        self.admin = AdminClient(self.config.configuration_dict)

    def set_propagator(self, propagator: object) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: An ITracePropagator instance.
        """
        self._propagator = propagator

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
        if _HAS_TRACING and self._propagator is not None:
            propagator: ITracePropagator = self._propagator  # type: ignore[assignment]  # guarded by _HAS_TRACING
            carrier = self._to_string_headers(message.headers())
            parent = propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        try:
            event_message: bytes | None = message.value()
            if event_message is None:  # pragma: no cover
                logger.warning(f"Received empty message for event type: {topic}")
                return
            event_data = self.type_adapters[event_type].validate_json(event_message)
            handlers = self.handlers[event_type]
            for handler in handlers:
                await handler(event_data)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error processing message for event type {topic}: {e}")
        finally:
            if _HAS_TRACING and self._propagator is not None:
                TraceContext.clear()

    def register(
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None:
        """Register an async handler for the given event type."""
        if event not in self.handlers:
            self.handlers[event] = []
            self.type_adapters[event] = TypeAdapter(event)
            self.type_lookup[event.__name__] = event
        self.handlers[event].append(handler)

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
