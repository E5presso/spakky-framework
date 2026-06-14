"""Configuration for the spakky-policy plugin."""

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration


@Configuration()
class SpakkyPolicyConfig(BaseSettings):
    """Runtime configuration for policy document loading."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="SPAKKY_POLICY_",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    document_path: Path | None = None
    """Optional YAML, TOML, or JSON policy document path."""

    def __init__(self) -> None:
        super().__init__()
