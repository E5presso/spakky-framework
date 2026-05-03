"""Redis cache backend configuration."""

from typing import ClassVar

from pydantic import NonNegativeInt, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_REDIS_CONFIG_ENV_PREFIX: str = "SPAKKY_REDIS__"


@Configuration()
class RedisCacheConfig(BaseSettings):
    """Redis cache backend configuration loaded from environment variables."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_REDIS_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    host: str = "localhost"
    """Redis server hostname."""

    port: PositiveInt = 6379
    """Redis server port."""

    db: NonNegativeInt = 0
    """Redis database index."""

    username: str | None = None
    """Optional Redis ACL username."""

    password: str | None = None
    """Optional Redis password."""

    use_ssl: bool = False
    """Use redis+ssl transport when true."""

    key_prefix: str = "spakky:cache:"
    """Prefix applied to keys managed by this cache backend."""

    socket_timeout: float = 5.0
    """Socket timeout in seconds for Redis operations."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def scheme(self) -> str:
        """Return the Redis URL scheme for this configuration."""
        return "rediss" if self.use_ssl else "redis"

    @property
    def connection_url(self) -> str:
        """Return a Redis connection URL without embedding credentials."""
        return f"{self.scheme}://{self.host}:{self.port}/{self.db}"
