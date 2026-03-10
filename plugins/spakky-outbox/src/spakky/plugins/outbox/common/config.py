"""Outbox configuration."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_OUTBOX_CONFIG_ENV_PREFIX: str = "SPAKKY_OUTBOX__"


@Configuration()
class OutboxConfig(BaseSettings):
    """Outbox plugin configuration loaded from environment variables."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_OUTBOX_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    polling_interval_seconds: float = 1.0
    batch_size: int = 100
    max_retry_count: int = 5

    def __init__(self) -> None:
        super().__init__()
