"""Celery configuration."""

from enum import Enum
from typing import Annotated, ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_CELERY_CONFIG_ENV_PREFIX: str = "SPAKKY_CELERY__"


def _validate_timezone(value: str) -> str:
    """Validate that the timezone string is a valid IANA timezone."""
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"Invalid timezone: {value}") from e
    return value


Timezone = Annotated[str, AfterValidator(_validate_timezone)]


class CelerySerializer(str, Enum):
    """Celery message serialization formats."""

    JSON = "json"
    PICKLE = "pickle"
    YAML = "yaml"
    MSGPACK = "msgpack"


@Configuration()
class CeleryConfig(BaseSettings):
    """Celery plugin configuration loaded from environment variables."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_CELERY_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    app_name: str = "spakky-celery"
    """Celery application name."""

    broker_url: str
    """Celery broker URL (e.g., 'amqp://user:pass@host:5672//')."""

    result_backend: str | None = None
    """Celery result backend URL. None disables result storage."""

    task_serializer: CelerySerializer = CelerySerializer.JSON
    """Serializer for task messages."""

    result_serializer: CelerySerializer = CelerySerializer.JSON
    """Serializer for task results."""

    accept_content: list[CelerySerializer] = [CelerySerializer.JSON]
    """Accepted content types for deserialization."""

    timezone: Timezone = "UTC"
    """Timezone for scheduled tasks (IANA timezone, e.g., 'UTC', 'Asia/Seoul')."""

    enable_utc: bool = True
    """Use UTC for internal datetime handling."""

    def __init__(self) -> None:
        super().__init__()
