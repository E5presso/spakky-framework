"""Configuration for RabbitMQ connections.

Provides configuration dataclass for RabbitMQ connection parameters including
host, port, credentials, and exchange settings.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration
from spakky.event.delivery import RetryPolicy

from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX


class RabbitMQAuthFailureAction(StrEnum):
    """Ack/nack action used when a protected RabbitMQ handler fails auth."""

    ACK = "ack"
    """Acknowledge and drop the message."""

    NACK_REQUEUE = "nack_requeue"
    """Negative-acknowledge and requeue the message."""

    NACK_DROP = "nack_drop"
    """Negative-acknowledge without requeueing the message."""


@Configuration()
class RabbitMQConnectionConfig(BaseSettings):
    """Configuration for RabbitMQ connection.

    Stores connection parameters and provides a formatted connection string
    for establishing RabbitMQ connections.

    Attributes:
        host: RabbitMQ server hostname.
        port: RabbitMQ server port.
        user: Username for authentication.
        password: Password for authentication.
        exchange_name: Optional exchange name for pub/sub routing.
        declare_default_queue: Whether transports declare the unnamed queue.
        retry: Retry policy applied to every subscriber independently.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=RABBITMQ_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    use_ssl: bool
    """Flag indicating whether to use SSL for the connection."""

    host: str
    """RabbitMQ server hostname or IP address."""

    port: int
    """RabbitMQ server port number."""

    user: str
    """Username for RabbitMQ authentication."""

    password: str
    """Password for RabbitMQ authentication."""

    exchange_name: str | None = None
    """Optional exchange name for pub/sub message routing.

    None publishes through the default exchange, which reaches only the queue
    named after the event. Named subscribers require an exchange.
    """

    declare_default_queue: bool = True
    """Whether transports declare (and bind) the queue named after the event.

    That queue belongs to the unnamed subscriber. Turn it off when every
    consumer of the published events is a named subscriber; otherwise the
    queue would only accumulate messages nobody consumes.
    """

    retry: RetryPolicy = RetryPolicy()
    """Retry limits, spacing and mode applied to each subscriber queue."""

    auth_challenge_action: RabbitMQAuthFailureAction = RabbitMQAuthFailureAction.ACK
    """Message action for missing, invalid, or expired snapshot decisions."""

    auth_deny_action: RabbitMQAuthFailureAction = RabbitMQAuthFailureAction.ACK
    """Message action for explicit DENY decisions from protected handlers."""

    auth_error_action: RabbitMQAuthFailureAction = (
        RabbitMQAuthFailureAction.NACK_REQUEUE
    )
    """Message action for retryable provider ERROR decisions."""

    @property
    def protocol(self) -> str:
        """Determine protocol based on SSL usage.

        Returns:
            'amqps' if SSL is enabled, otherwise 'amqp'.
        """
        return "amqps" if self.use_ssl else "amqp"

    @property
    def connection_string(self) -> str:
        """Generate AMQP connection string from configuration.

        Returns:
            Formatted AMQP connection string with credentials and host information.
        """
        return f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}"

    def __init__(self) -> None:
        super().__init__()
