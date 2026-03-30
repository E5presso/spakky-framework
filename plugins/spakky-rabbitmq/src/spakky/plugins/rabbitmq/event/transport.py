"""RabbitMQ event transports for integration events.

Provides synchronous and asynchronous event transports that send integration
events to RabbitMQ queues with optional exchange routing.
"""

from aio_pika import (  # type: ignore[import-untyped]  # aio_pika lacks type stubs
    Message,
    connect_robust,
)
from pika import BasicProperties, BlockingConnection, URLParameters
from spakky.core.pod.annotations.pod import Pod
from spakky.event.event_publisher import (
    IAsyncEventTransport,
    IEventTransport,
)

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig


@Pod()
class RabbitMQEventTransport(IEventTransport):
    """Synchronous RabbitMQ event transport.

    Sends pre-serialized event payloads to RabbitMQ queues using blocking connections.
    Optionally routes through an exchange for pub/sub patterns.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Optional exchange name for routing.
    """

    connection_string: str
    exchange_name: str | None

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the synchronous RabbitMQ event transport.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Send a pre-serialized event payload to RabbitMQ.

        Creates a new connection, sends the payload to the appropriate queue,
        and closes the connection.

        Args:
            event_name: Routing key / queue name for the event.
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
        """
        connection = BlockingConnection(URLParameters(self.connection_string))
        channel = connection.channel()
        channel.queue_declare(event_name)
        if self.exchange_name is not None:
            channel.exchange_declare(self.exchange_name)
            channel.queue_bind(event_name, self.exchange_name, event_name)
        channel.basic_publish(
            self.exchange_name if self.exchange_name is not None else "",
            event_name,
            payload,
            properties=BasicProperties(headers=headers),
        )
        channel.close()
        connection.close()


@Pod()
class AsyncRabbitMQEventTransport(IAsyncEventTransport):
    """Asynchronous RabbitMQ event transport.

    Sends pre-serialized event payloads to RabbitMQ queues using async connections.
    Optionally routes through an exchange for pub/sub patterns.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Optional exchange name for routing.
    """

    connection_string: str
    exchange_name: str | None

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the asynchronous RabbitMQ event transport.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Send a pre-serialized event payload to RabbitMQ asynchronously.

        Creates a new robust connection, sends the payload to the appropriate
        queue, and closes the connection.

        Args:
            event_name: Routing key / queue name for the event.
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
        """
        async with await connect_robust(self.connection_string) as connection:
            channel = await connection.channel()
            exchange = (
                await channel.declare_exchange(self.exchange_name)
                if self.exchange_name is not None
                else channel.default_exchange
            )
            queue = await channel.declare_queue(event_name)
            if self.exchange_name is not None:
                await queue.bind(exchange, event_name)
            await exchange.publish(
                Message(body=payload, headers=dict(headers)),
                routing_key=event_name,
            )
            await channel.close()
