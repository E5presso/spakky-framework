"""Plugin initialization for gRPC integration.

Registers post-processors that enable automatic gRPC service registration,
interceptor injection, and server lifecycle management.
"""

from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
)
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec


def initialize(app: SpakkyApplication) -> None:
    """Initialize the gRPC plugin.

    Registers post-processors for automatic gRPC service registration,
    interceptor injection, and server lifecycle management.  This
    function is called automatically by the Spakky framework during
    plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(GrpcConfig)
    app.add(descriptor_registry)
    app.add(grpc_server_spec)
    app.add(RegisterServicesPostProcessor)
    app.add(AddInterceptorsPostProcessor)
    app.add(BindServerPostProcessor)


@Pod(name="descriptor_registry")
def descriptor_registry() -> DescriptorRegistry:
    """Create the shared protobuf descriptor registry."""
    return DescriptorRegistry()


@Pod(name="grpc_server_spec")
def grpc_server_spec(config: GrpcConfig) -> GrpcServerSpec:
    """Create the shared gRPC server spec from plugin configuration."""
    spec = GrpcServerSpec()
    for address in config.bind_addresses:
        spec.add_insecure_port(address)
    return spec
