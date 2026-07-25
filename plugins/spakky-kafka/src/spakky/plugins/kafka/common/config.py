"""Configuration for Kafka connections.

Provides configuration dataclass for Kafka connection parameters including
bootstrap servers, consumer group, and security settings.
"""

from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import NonNegativeInt, PositiveFloat, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX


class AutoOffsetResetType(StrEnum):
    """Kafka consumer auto offset reset policies."""

    EARLIEST = "earliest"
    LATEST = "latest"
    NONE = "none"


@Configuration()
class KafkaConnectionConfig(BaseSettings):
    """Kafka connection configuration loaded from environment variables."""

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

    poll_timeout: float = 1.0
    """Consumer poll timeout in seconds."""

    dead_letter_topic_suffix: Annotated[str, StringConstraints(min_length=1)] = ".dlt"
    """Suffix appended to the original topic name to build its dead-letter topic.

    An empty suffix would make the dead-letter topic the original topic itself,
    republishing every failure back into the stream it came from, so it is rejected.
    """

    max_handler_retries: NonNegativeInt = 0
    """How many times a failed handler dispatch is retried before dead-lettering.

    Retrying re-invokes every handler registered for the event, so handlers must
    be idempotent when this is raised above zero. Deserialization failures never
    succeed on retry and are dead-lettered immediately regardless of this value.
    """

    dead_letter_delivery_timeout: PositiveFloat = 10.0
    """Seconds to wait for a dead-letter record to reach the broker.

    Bounds how long the consumer blocks on one failed message; without it a broker
    outage would stall the poll loop until the client's own message timeout.
    """

    def __init__(self) -> None:
        super().__init__()

    @property
    def configuration_dict(self) -> dict[str, str | int | float | bool]:
        config: dict[str, str | int | float | bool] = {
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

    @property
    def async_producer_configuration_dict(self) -> dict[str, str]:
        """Same connection settings rendered as `aiokafka.AIOKafkaProducer` keywords.

        `aiokafka` takes snake_case keywords instead of the dotted librdkafka
        property names in `configuration_dict`, so every async producer in this
        plugin reads its settings here rather than mapping them again.
        """
        config = {
            "bootstrap_servers": self.bootstrap_servers,
            "client_id": self.client_id,
        }
        if self.security_protocol:
            config["security_protocol"] = self.security_protocol
        if self.sasl_mechanism:
            config["sasl_mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            config["sasl_plain_username"] = self.sasl_username
        if self.sasl_password:
            config["sasl_plain_password"] = self.sasl_password
        return config
