"""Plugin initialization for gRPC integration.

Registers post-processors that enable automatic gRPC service registration
and server lifecycle management.
"""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the gRPC plugin.

    Post-processors for gRPC service registration will be added
    in subsequent tasks.

    Args:
        app: The Spakky application instance.
    """
