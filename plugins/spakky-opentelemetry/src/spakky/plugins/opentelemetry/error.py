"""Error classes for the spakky-opentelemetry package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyOpenTelemetryError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all OpenTelemetry plugin errors."""

    ...


class UnsupportedExporterTypeError(AbstractSpakkyOpenTelemetryError):
    """Raised when the configured exporter type is not supported."""

    message = "Unsupported exporter type"
