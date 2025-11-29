"""RabbitMQ event consumers for domain events.

Provides synchronous and asynchronous event consumers that run as background
services, consuming domain events from RabbitMQ queues and dispatching them
to registered handlers.
"""

from typing import Any

from aio_pika import connect_robust  # pyrefly: ignore  # type: ignore
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from pika import URLParameters
from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
from pika.spec import Basic, BasicProperties
from pydantic import TypeAdapter
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.error import (
    DuplicateEventHandlerError,
    InvalidMessageError,
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

from spakky_rabbitmq.common.config import RabbitMQConnectionConfig


@Pod(scope=Pod.Scope.CONTEXT)
class RabbitMQEventConsumer(IEventConsumer, AbstractBackgroundService):
    """Synchronous RabbitMQ event consumer.

    Runs as a background service that consumes domain events from RabbitMQ
    queues and dispatches them to registered synchronous event handlers.
    Uses blocking connection for synchronous event processing.

    Attributes:
        connection_string: AMQP connection string.
        type_lookup: Maps consumer tags to event types.
        handlers: Maps event types to handler callbacks.
        connection: Blocking RabbitMQ connection.
        channel: Blocking channel for message consumption.
    """

    connection_string: str
    type_lookup: dict[str, type[AbstractDomainEvent]]
    type_adapters: dict[type, TypeAdapter[AbstractDomainEvent]]
    handlers: dict[type[AbstractDomainEvent], IEventHandlerCallback[Any]]
    connection: BlockingConnection
    channel: BlockingChannel

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the synchronous RabbitMQ event consumer.

        Args:
            config: RabbitMQ connection configuration.
        """
        super().__init__()
        self.connection_string = config.connection_string
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}

    def _route_event_handler(
        self,
        channel: BlockingChannel,
        method_frame: Basic.Deliver,
        _: BasicProperties,
        body: bytes,
    ) -> None:
        if method_frame.consumer_tag is None or method_frame.delivery_tag is None:
            raise InvalidMessageError("Missing consumer tag or delivery tag.")
        event_type = self.type_lookup[method_frame.consumer_tag]
        handler = self.handlers[event_type]
        type_adapter = self.type_adapters[event_type]
        event = type_adapter.validate_json(body)
        handler(event)
        channel.basic_ack(method_frame.delivery_tag)

    def _check_if_event_set(self) -> None:
        if self._stop_event.is_set():
            self.channel.stop_consuming()
        self.connection.add_callback_threadsafe(self._check_if_event_set)

    def register(
        self,
        event: type[DomainEventT],
        handler: IEventHandlerCallback[DomainEventT],
    ) -> None:
        """Register an event handler for a specific event type.

        Only one handler can be registered per event type. Attempting to
        register multiple handlers for the same event will raise an error.

        Args:
            event: The event type to handle.
            handler: The callback function to handle the event.

        Raises:
            DuplicateEventHandlerError: If a handler is already registered for this event type.
        """
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)

    def initialize(self) -> None:
        """Initialize RabbitMQ connection and declare queues.

        Establishes connection to RabbitMQ, creates a channel, and sets up
        queue consumers for all registered event handlers.
        """
        self.connection = BlockingConnection(
            parameters=URLParameters(self.connection_string)
        )
        self.channel = self.connection.channel()

        for event_type in self.handlers:
            self.channel.queue_declare(event_type.__name__)
            consumer_tag = self.channel.basic_consume(
                event_type.__name__,
                self._route_event_handler,
            )
            self.type_lookup[consumer_tag] = event_type

    def dispose(self) -> None:
        """Clean up RabbitMQ resources.

        Closes the channel and connection when the service is stopped.
        """
        self.channel.close()
        self.connection.close()
        return

    def run(self) -> None:
        """Run the event consumer loop.

        Starts consuming messages from RabbitMQ queues and blocks until
        the stop event is set.
        """
        self.connection.add_callback_threadsafe(self._check_if_event_set)
        self.channel.start_consuming()


@Pod(scope=Pod.Scope.CONTEXT)
class AsyncRabbitMQEventConsumer(IAsyncEventConsumer, AbstractAsyncBackgroundService):
    """Asynchronous RabbitMQ event consumer.

    Runs as an async background service that consumes domain events from
    RabbitMQ queues and dispatches them to registered asynchronous event
    handlers. Uses robust connection for automatic reconnection.

    Attributes:
        connection_string: AMQP connection string.
        type_lookup: Maps consumer tags to event types.
        handlers: Maps event types to async handler callbacks.
        connection: Robust RabbitMQ connection for async operations.
    """

    connection_string: str
    type_lookup: dict[str, type[AbstractDomainEvent]]
    type_adapters: dict[type, TypeAdapter[AbstractDomainEvent]]
    handlers: dict[type[AbstractDomainEvent], IAsyncEventHandlerCallback[Any]]
    connection: AbstractRobustConnection

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the asynchronous RabbitMQ event consumer.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.type_lookup = {}
        self.type_adapters = {}
        self.handlers = {}

    async def _route_event_handler(self, message: AbstractIncomingMessage) -> None:
        if message.consumer_tag is None or message.delivery_tag is None:
            raise InvalidMessageError("Missing consumer tag or delivery tag.")
        event_type = self.type_lookup[message.consumer_tag]
        handler = self.handlers[event_type]
        type_adapter = self.type_adapters[event_type]
        event = type_adapter.validate_json(message.body)
        await handler(event)
        await message.ack()

    def register(
        self,
        event: type[DomainEventT],
        handler: IAsyncEventHandlerCallback[DomainEventT],
    ) -> None:
        """Register an async event handler for a specific event type.

        Only one handler can be registered per event type. Attempting to
        register multiple handlers for the same event will raise an error.

        Args:
            event: The event type to handle.
            handler: The async callback function to handle the event.

        Raises:
            DuplicateEventHandlerError: If a handler is already registered for this event type.
        """
        if event in self.handlers:
            raise DuplicateEventHandlerError(event)
        self.handlers[event] = handler
        self.type_adapters[event] = TypeAdapter(event)

    async def initialize_async(self) -> None:
        """Initialize async RabbitMQ connection and declare queues.

        Establishes robust connection to RabbitMQ, creates a channel, and sets
        up queue consumers for all registered async event handlers.
        """
        self.connection = await connect_robust(self.connection_string)
        self.channel = await self.connection.channel()

        for event_type in self.handlers:
            queue = await self.channel.declare_queue(event_type.__name__)
            consumer_tag = await queue.consume(self._route_event_handler)
            self.type_lookup[consumer_tag] = event_type

    async def dispose_async(self) -> None:
        """Clean up async RabbitMQ resources.

        Closes the channel and connection when the service is stopped.
        """
        await self.channel.close()
        await self.connection.close()
        return

    async def run_async(self) -> None:
        """Run the async event consumer loop.

        Waits for the stop event to be set while consuming messages from
        RabbitMQ queues in the background.
        """
        await self._stop_event.wait()
