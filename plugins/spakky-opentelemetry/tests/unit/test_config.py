"""Tests for OpenTelemetryConfig."""

import os
from unittest.mock import patch

from spakky.plugins.opentelemetry.config import ExporterType, OpenTelemetryConfig


def test_config_default_values() -> None:
    """기본값으로 설정이 생성된다."""
    config = OpenTelemetryConfig()

    assert config.service_name == "spakky-service"
    assert config.exporter_type == ExporterType.OTLP
    assert config.exporter_endpoint == "http://localhost:4317"
    assert config.sample_rate == 1.0


def test_config_env_override_service_name() -> None:
    """SPAKKY_OTEL_SERVICE_NAME 환경변수로 service_name을 오버라이드한다."""
    with patch.dict(os.environ, {"SPAKKY_OTEL_SERVICE_NAME": "my-service"}):
        config = OpenTelemetryConfig()

    assert config.service_name == "my-service"


def test_config_env_override_exporter_type() -> None:
    """SPAKKY_OTEL_EXPORTER_TYPE 환경변수로 exporter_type을 오버라이드한다."""
    with patch.dict(os.environ, {"SPAKKY_OTEL_EXPORTER_TYPE": "console"}):
        config = OpenTelemetryConfig()

    assert config.exporter_type == ExporterType.CONSOLE


def test_config_env_override_exporter_endpoint() -> None:
    """SPAKKY_OTEL_EXPORTER_ENDPOINT 환경변수로 endpoint를 오버라이드한다."""
    with patch.dict(os.environ, {"SPAKKY_OTEL_EXPORTER_ENDPOINT": "http://otel:4317"}):
        config = OpenTelemetryConfig()

    assert config.exporter_endpoint == "http://otel:4317"


def test_config_env_override_sample_rate() -> None:
    """SPAKKY_OTEL_SAMPLE_RATE 환경변수로 sample_rate를 오버라이드한다."""
    with patch.dict(os.environ, {"SPAKKY_OTEL_SAMPLE_RATE": "0.5"}):
        config = OpenTelemetryConfig()

    assert config.sample_rate == 0.5


def test_exporter_type_otlp_value() -> None:
    """OTLP 값은 'otlp'이다."""
    assert ExporterType.OTLP == "otlp"


def test_exporter_type_console_value() -> None:
    """CONSOLE 값은 'console'이다."""
    assert ExporterType.CONSOLE == "console"


def test_exporter_type_none_value() -> None:
    """NONE 값은 'none'이다."""
    assert ExporterType.NONE == "none"
