from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.outbox.common.constants import SPAKKY_OUTBOX_CONFIG_ENV_PREFIX


@Configuration()
class OutboxConfig(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_OUTBOX_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    polling_interval_seconds: float = 1.0
    """Seconds to wait between relay polling cycles."""

    batch_size: int = 100
    """Maximum number of outbox messages to process per polling cycle."""

    max_retry_count: int = 5
    """Maximum number of delivery attempts before a message is skipped."""

    def __init__(self) -> None:
        super().__init__()
