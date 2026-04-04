"""OpenTelemetry plugin configuration."""

from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from spakky.core.stereotype.configuration import Configuration

OTEL_CONFIG_ENV_PREFIX = "OTEL_"


class ExporterType(StrEnum):
    """Supported span exporter types."""

    OTLP = "otlp"
    CONSOLE = "console"
    NONE = "none"


@Configuration()
class OpenTelemetryConfig(BaseSettings):
    """Configuration for the OpenTelemetry SDK bridge.

    Attributes:
        service_name: OTel service name for resource identification.
        exporter_type: Span exporter backend (otlp, console, none).
        exporter_endpoint: OTLP collector endpoint URL.
        sample_rate: Trace sampling rate (0.0 to 1.0).
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=OTEL_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
    )

    service_name: str = "spakky-service"
    exporter_type: ExporterType = ExporterType.OTLP
    exporter_endpoint: str = "http://localhost:4317"
    sample_rate: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0

    def __init__(self) -> None:
        super().__init__()
