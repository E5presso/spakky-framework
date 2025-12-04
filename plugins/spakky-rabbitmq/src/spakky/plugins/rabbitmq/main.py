"""Plugin initialization for RabbitMQ integration.

Registers event consumers, publishers, and post-processors for automatic
event handler registration in RabbitMQ-enabled applications.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
from spakky.plugins.rabbitmq.event.consumer import (
    AsyncRabbitMQEventConsumer,
    RabbitMQEventConsumer,
)
from spakky.plugins.rabbitmq.event.publisher import (
    AsyncRabbitMQEventPublisher,
    RabbitMQEventPublisher,
)
from spakky.plugins.rabbitmq.post_processor import RabbitMQPostProcessor


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
