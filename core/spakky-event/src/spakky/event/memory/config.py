"""Configuration of the in-memory integration event broker."""

from typing import ClassVar

from pydantic import PositiveFloat
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.event.delivery import RetryPolicy

SPAKKY_EVENT_MEMORY_CONFIG_ENV_PREFIX = "SPAKKY_EVENT_MEMORY__"


@Configuration()
class InMemoryEventConfig(BaseSettings):
    """Retry and polling settings of the in-memory broker."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_EVENT_MEMORY_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    retry: RetryPolicy = RetryPolicy()
    """Retry limits applied to each subscriber independently."""

    poll_interval: PositiveFloat = 0.05
    """Seconds a background consumer waits before looking for new messages."""

    def __init__(self) -> None:
        super().__init__()
