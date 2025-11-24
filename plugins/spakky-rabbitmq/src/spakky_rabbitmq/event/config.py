"""Configuration for RabbitMQ connections.

Provides configuration dataclass for RabbitMQ connection parameters including
host, port, credentials, and exchange settings.
"""

from dataclasses import dataclass


@dataclass
class RabbitMQConnectionConfig:
    """Configuration for RabbitMQ connection.

    Stores connection parameters and provides a formatted connection string
    for establishing RabbitMQ connections.

    Attributes:
        host: RabbitMQ server hostname.
        port: RabbitMQ server port.
        user: Username for authentication.
        password: Password for authentication.
        exchange_name: Optional exchange name for pub/sub routing.
    """

    host: str
    """RabbitMQ server hostname or IP address."""

    port: int
    """RabbitMQ server port number."""

    user: str
    """Username for RabbitMQ authentication."""

    password: str
    """Password for RabbitMQ authentication."""

    exchange_name: str | None
    """Optional exchange name for pub/sub message routing."""

    @property
    def connection_string(self) -> str:
        """Generate AMQP connection string from configuration.

        Returns:
            Formatted AMQP connection string with credentials and host information.
        """
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}"
