"""Tests for error classes."""

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.plugins.opentelemetry.error import (
    AbstractSpakkyOpenTelemetryError,
    UnsupportedExporterTypeError,
)


def test_abstract_error_is_framework_error() -> None:
    """AbstractSpakkyOpenTelemetryError는 AbstractSpakkyFrameworkError의 하위 클래스이다."""
    assert issubclass(AbstractSpakkyOpenTelemetryError, AbstractSpakkyFrameworkError)


def test_unsupported_exporter_type_error_is_opentelemetry_error() -> None:
    """UnsupportedExporterTypeError는 AbstractSpakkyOpenTelemetryError의 하위 클래스이다."""
    assert issubclass(UnsupportedExporterTypeError, AbstractSpakkyOpenTelemetryError)


def test_unsupported_exporter_type_error_message() -> None:
    """UnsupportedExporterTypeError의 message가 정의되어 있다."""
    assert UnsupportedExporterTypeError.message == "Unsupported exporter type"
