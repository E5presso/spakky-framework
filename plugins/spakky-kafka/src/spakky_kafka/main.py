from spakky.application.application import SpakkyApplication

from spakky_kafka.common.config import KafkaConnectionConfig


def initialize(app: SpakkyApplication) -> None:
    app.add(KafkaConnectionConfig)
