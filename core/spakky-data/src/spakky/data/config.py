"""Shared persistence execution-mode configuration."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_DATA_CONFIG_ENV_PREFIX: str = "SPAKKY_DATA__"


@Configuration()
class DataConfig(BaseSettings):
    """Control asynchronous transaction support across data and provider plugins."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_DATA_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    support_async_mode: bool = True
    """Register async transactional aspects and provider Pods in addition to sync ones."""

    def __init__(self) -> None:
        """Read the common data configuration from environment variables."""
        super().__init__()
