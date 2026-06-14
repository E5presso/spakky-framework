"""FastAPI configuration for actuator HTTP endpoints."""

from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_FASTAPI_ACTUATOR_CONFIG_ENV_PREFIX = "SPAKKY_FASTAPI_ACTUATOR_"


@Configuration()
class FastAPIActuatorConfig(BaseSettings):
    """FastAPI actuator endpoint exposure settings loaded from environment."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_FASTAPI_ACTUATOR_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    enabled: bool = True
    base_path: str = "/actuator"
    health_enabled: bool = True
    readiness_enabled: bool = True
    liveness_enabled: bool = True
    info_enabled: bool = True

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, base_path: str) -> str:
        """Normalize actuator base path to the shape FastAPI expects."""
        stripped = base_path.strip("/")
        if not stripped:
            return ""
        return f"/{stripped}"

    def __init__(self) -> None:
        super().__init__()
