"""Logging configuration for Spakky Framework.

Provides a Configuration that controls how the framework's
logging system is set up: format, levels, masking, and slow-call thresholds.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.logging.constants import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_MASK_KEYS,
    DEFAULT_MASK_REPLACEMENT,
    DEFAULT_MAX_RESULT_LENGTH,
    DEFAULT_SLOW_THRESHOLD_MS,
    SPAKKY_LOGGING_CONFIG_ENV_PREFIX,
)


class LogFormat(StrEnum):
    """Supported log output formats."""

    TEXT = "text"
    JSON = "json"
    PRETTY = "pretty"


@Configuration()
class LoggingConfig(BaseSettings):
    """Configuration for the Spakky logging system.

    Attributes:
        level: Root logger level (e.g. ``logging.INFO``, ``logging.DEBUG``).
        format: Output format — ``text``, ``json``, or ``pretty``.
        date_format: ``strftime`` pattern for timestamps.
        package_levels: Per-logger level overrides, keyed by logger name.
        mask_keys: Global list of sensitive keys to mask in ``@Logging`` output.
        mask_replacement: Replacement text for masked values.
        slow_threshold_ms: Millisecond threshold for slow-call warnings in ``@Logging``.
        max_result_length: Maximum character length for result ``repr`` in ``@Logging``.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_LOGGING_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    level: int = logging.INFO
    format: LogFormat = LogFormat.TEXT
    date_format: str = DEFAULT_DATE_FORMAT
    package_levels: dict[str, int] = {}
    mask_keys: list[str] = DEFAULT_MASK_KEYS
    mask_replacement: str = DEFAULT_MASK_REPLACEMENT
    slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS
    max_result_length: int = DEFAULT_MAX_RESULT_LENGTH

    def __init__(self) -> None:
        super().__init__()
