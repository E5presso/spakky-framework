"""Plugin initialization entry point for spakky-opentelemetry."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.opentelemetry.config import OpenTelemetryConfig
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-opentelemetry plugin.

    Registers the OpenTelemetry configuration and the post-processor
    that sets up TracerProvider and replaces W3CTracePropagator.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(OpenTelemetryConfig)
    app.add(OTelSetupPostProcessor)
