"""Plugin initialization for gRPC integration.

Registers post-processors that enable automatic gRPC service registration,
interceptor injection, and server lifecycle management.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
)
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)


def initialize(app: SpakkyApplication) -> None:
    """Initialize the gRPC plugin.

    Registers post-processors for automatic gRPC service registration,
    interceptor injection, and server lifecycle management.  This
    function is called automatically by the Spakky framework during
    plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(RegisterServicesPostProcessor)
    app.add(AddInterceptorsPostProcessor)
    app.add(BindServerPostProcessor)
