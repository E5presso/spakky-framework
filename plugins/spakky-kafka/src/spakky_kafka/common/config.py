"""Configuration for RabbitMQ connections.

Provides configuration dataclass for RabbitMQ connection parameters including
host, port, credentials, and exchange settings.
"""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.stereotype.configuration import Configuration

from spakky_kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX


@Configuration()
class KafkaConnectionConfig(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_KAFKA_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    bootstrap_servers: str
    """Kafka bootstrap servers."""

    security_protocol: str | None
    """Security protocol for Kafka connection."""

    sasl_mechanism: str | None
    """SASL mechanism for Kafka authentication."""

    sasl_username: str | None
    """SASL username for Kafka authentication."""

    sasl_password: str | None
    """SASL password for Kafka authentication."""

    def __init__(self) -> None:
        super().__init__()
