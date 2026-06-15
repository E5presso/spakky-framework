"""FastAPI application configuration."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_FASTAPI_CONFIG_ENV_PREFIX = "SPAKKY_FASTAPI_"
"""Environment prefix for the default FastAPI application settings."""


@Configuration()
class FastAPIConfig(BaseSettings):
    """Settings used by the plugin-provided default FastAPI application."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_FASTAPI_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        frozen=True,
    )

    title: str = "Spakky API"
    description: str = ""
    version: str = "0.1.0"
    debug: bool = False

    def __init__(self) -> None:
        super().__init__()
