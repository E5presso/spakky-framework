"""Plugin initialization for RabbitMQ integration.

Registers event consumers, publishers, and post-processors for automatic
event handler registration in RabbitMQ-enabled applications.
"""

from spakky.application.application import SpakkyApplication

from spakky_rabbitmq.common.config import RabbitMQConnectionConfig
from spakky_rabbitmq.event.consumer import (
    AsyncRabbitMQEventConsumer,
    RabbitMQEventConsumer,
)
from spakky_rabbitmq.event.publisher import (
    AsyncRabbitMQEventPublisher,
    RabbitMQEventPublisher,
)
from spakky_rabbitmq.post_processor import RabbitMQPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the RabbitMQ plugin.

    Registers event consumers, publishers, and the post-processor for automatic
    event handler registration. This function is called automatically by the
    Spakky framework during plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(RabbitMQConnectionConfig)

    app.add(RabbitMQPostProcessor)

    app.add(RabbitMQEventConsumer)
    app.add(RabbitMQEventPublisher)

    app.add(AsyncRabbitMQEventConsumer)
    app.add(AsyncRabbitMQEventPublisher)
