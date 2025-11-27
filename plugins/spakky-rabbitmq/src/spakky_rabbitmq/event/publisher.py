"""RabbitMQ event publishers for domain events.

Provides synchronous and asynchronous event publishers that publish domain
events to RabbitMQ queues with optional exchange routing.
"""

from aio_pika import Message, connect_robust  # pyrefly: ignore  # type: ignore
from pika import BlockingConnection, URLParameters
from pydantic import TypeAdapter
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)
from spakky.pod.annotations.pod import Pod

from spakky_rabbitmq.event.config import RabbitMQConnectionConfig


@Pod()
class RabbitMQEventPublisher(IEventPublisher):
    """Synchronous RabbitMQ event publisher.

    Publishes domain events to RabbitMQ queues using blocking connections.
    Optionally routes through an exchange for pub/sub patterns.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Optional exchange name for routing.
    """

    connection_string: str
    exchange_name: str | None
    type_adapters: dict[type, TypeAdapter[AbstractDomainEvent]]

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the synchronous RabbitMQ event publisher.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name
        self.type_adapters = {}

    def publish(self, event: AbstractDomainEvent) -> None:
        """Publish a domain event to RabbitMQ.

        Creates a new connection, publishes the event to the appropriate queue,
        and closes the connection.

        Args:
            event: The domain event to publish.
        """
        connection = BlockingConnection(URLParameters(self.connection_string))
        channel = connection.channel()
        channel.queue_declare(event.event_name)
        if self.exchange_name is not None:
            channel.exchange_declare(self.exchange_name)
            channel.queue_bind(event.event_name, self.exchange_name, event.event_name)
        if type(event) not in self.type_adapters:
            self.type_adapters[type(event)] = TypeAdapter(type(event))
        channel.basic_publish(
            self.exchange_name if self.exchange_name is not None else "",
            event.event_name,
            self.type_adapters[type(event)].dump_json(event),
        )
        channel.close()
        connection.close()


@Pod()
class AsyncRabbitMQEventPublisher(IAsyncEventPublisher):
    """Asynchronous RabbitMQ event publisher.

    Publishes domain events to RabbitMQ queues using async connections.
    Optionally routes through an exchange for pub/sub patterns.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Optional exchange name for routing.
    """

    connection_string: str
    exchange_name: str | None
    type_adapters: dict[type, TypeAdapter[AbstractDomainEvent]]

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the asynchronous RabbitMQ event publisher.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name
        self.type_adapters = {}

    async def publish(self, event: AbstractDomainEvent) -> None:
        """Publish a domain event to RabbitMQ asynchronously.

        Creates a new robust connection, publishes the event to the appropriate
        queue, and closes the connection.

        Args:
            event: The domain event to publish.
        """
        async with await connect_robust(self.connection_string) as connection:
            channel = await connection.channel()
            exchange = (
                await channel.declare_exchange(self.exchange_name)
                if self.exchange_name is not None
                else channel.default_exchange
            )
            queue = await channel.declare_queue(event.event_name)
            if self.exchange_name is not None:
                await queue.bind(exchange, event.event_name)
            if type(event) not in self.type_adapters:
                self.type_adapters[type(event)] = TypeAdapter(type(event))
            await exchange.publish(
                Message(body=self.type_adapters[type(event)].dump_json(event)),
                routing_key=event.event_name,
            )
            await channel.close()
