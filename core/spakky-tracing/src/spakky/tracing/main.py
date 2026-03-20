"""Plugin initialization entry point for spakky-tracing."""

from spakky.core.application.application import SpakkyApplication
from spakky.tracing.w3c_propagator import W3CTracePropagator


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-tracing plugin.

    Registers the W3CTracePropagator as the default trace context propagator.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(W3CTracePropagator)
