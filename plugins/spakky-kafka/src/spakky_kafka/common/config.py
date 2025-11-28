"""Configuration for RabbitMQ connections.

Provides configuration dataclass for RabbitMQ connection parameters including
host, port, credentials, and exchange settings.
"""

from enum import Enum
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.stereotype.configuration import Configuration

from spakky_kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX


class AutoOffsetResetType(str, Enum):
    """Kafka consumer auto offset reset policies."""

    EARLIEST = "earliest"
    LATEST = "latest"
    NONE = "none"


@Configuration()
class KafkaConnectionConfig(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_KAFKA_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    group_id: str
    """Kafka consumer group identifier."""

    client_id: str
    """Kafka client identifier."""

    bootstrap_servers: str
    """Kafka bootstrap servers."""

    security_protocol: str | None = None
    """Security protocol for Kafka connection."""

    sasl_mechanism: str | None = None
    """SASL mechanism for Kafka authentication."""

    sasl_username: str | None = None
    """SASL username for Kafka authentication."""

    sasl_password: str | None = None
    """SASL password for Kafka authentication."""

    number_of_partitions: int = 1
    """Default number of partitions for created topics."""

    replication_factor: int = 1
    """Default replication factor for created topics."""

    auto_offset_reset: AutoOffsetResetType = AutoOffsetResetType.EARLIEST
    """Consumer auto offset reset policy (earliest, latest, none)."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def configuration_dict(self) -> dict[str, str]:
        config = {
            "group.id": self.group_id,
            "client.id": self.client_id,
            "bootstrap.servers": self.bootstrap_servers,
            "auto.offset.reset": self.auto_offset_reset.value,
        }
        if self.security_protocol:
            config["security.protocol"] = self.security_protocol
        if self.sasl_mechanism:
            config["sasl.mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            config["sasl.username"] = self.sasl_username
        if self.sasl_password:
            config["sasl.password"] = self.sasl_password
        return config
