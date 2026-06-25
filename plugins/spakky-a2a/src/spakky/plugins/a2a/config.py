"""A2A plugin configuration."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_A2A_CONFIG_ENV_PREFIX = "SPAKKY_A2A_"
"""Environment prefix for A2A plugin settings."""

DEFAULT_A2A_BASE_URL = "http://localhost:8000"
"""Fallback base URL advertised on a derived AgentCard interface."""

DEFAULT_A2A_VERSION = "1.0.0"
"""Fallback semantic version advertised on a derived AgentCard."""


@Configuration()
class A2AConfig(BaseSettings):
    """Configuration for the A2A protocol server integration."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_A2A_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    default_base_url: str = DEFAULT_A2A_BASE_URL
    """Base URL advertised on a derived AgentCard transport interface."""

    default_version: str = DEFAULT_A2A_VERSION
    """Semantic version advertised on a derived AgentCard."""

    def __init__(self) -> None:
        super().__init__()
