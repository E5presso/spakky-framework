"""Plugin initialization entry point for spakky-opentelemetry."""

from spakky.agent.telemetry import IAgentTelemetry
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.opentelemetry.bridge import LogContextBridge
from spakky.plugins.opentelemetry.config import OpenTelemetryConfig
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor
from spakky.plugins.opentelemetry.telemetry import OpenTelemetryAgentTelemetry


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-opentelemetry plugin.

    Registers the OpenTelemetry configuration, the post-processor
    that sets up TracerProvider and replaces W3CTracePropagator,
    the LogContextBridge for optional trace-to-logging sync, and the
    Agent telemetry bridge without replacing either existing integration.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(OpenTelemetryConfig)
    app.add(OTelSetupPostProcessor)
    app.add(LogContextBridge)
    app.add(OpenTelemetryAgentTelemetry)
    app.container.bind_to_type(IAgentTelemetry, OpenTelemetryAgentTelemetry)
