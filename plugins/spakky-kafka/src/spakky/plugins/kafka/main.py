from spakky.core.application.application import SpakkyApplication

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)
from spakky.plugins.kafka.event.publisher import (
    AsyncKafkaEventPublisher,
    KafkaEventPublisher,
)
from spakky.plugins.kafka.post_processor import KafkaPostProcessor


def initialize(app: SpakkyApplication) -> None:
    app.add(KafkaConnectionConfig)

    app.add(KafkaEventConsumer)
    app.add(KafkaEventPublisher)

    app.add(AsyncKafkaEventConsumer)
    app.add(AsyncKafkaEventPublisher)

    app.add(KafkaPostProcessor)
