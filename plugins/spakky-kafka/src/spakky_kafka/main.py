from spakky.application.application import SpakkyApplication

from spakky_kafka.common.config import KafkaConnectionConfig
from spakky_kafka.event.consumer import AsyncKafkaEventConsumer, KafkaEventConsumer
from spakky_kafka.event.publisher import AsyncKafkaEventPublisher, KafkaEventPublisher
from spakky_kafka.post_processor import KafkaPostProcessor


def initialize(app: SpakkyApplication) -> None:
    app.add(KafkaConnectionConfig)

    app.add(KafkaEventConsumer)
    app.add(KafkaEventPublisher)

    app.add(AsyncKafkaEventConsumer)
    app.add(AsyncKafkaEventPublisher)

    app.add(KafkaPostProcessor)
