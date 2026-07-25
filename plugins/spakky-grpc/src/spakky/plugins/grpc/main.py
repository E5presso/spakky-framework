"""Plugin initialization for gRPC integration.

Registers post-processors that enable automatic gRPC service registration,
interceptor injection, and server lifecycle management.
"""

from grpc_health.v1 import health
from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.credentials import build_server_credentials
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
from spakky.plugins.grpc.standard_services import (
    enable_health_service,
    enable_reflection_service,
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
    app.add(GrpcConfig)
    app.add(descriptor_registry)
    app.add(grpc_health_servicer)
    app.add(grpc_server_spec)
    app.add(RegisterServicesPostProcessor)
    app.add(AddInterceptorsPostProcessor)
    app.add(BindServerPostProcessor)


@Pod(name="descriptor_registry")
def descriptor_registry() -> DescriptorRegistry:
    """Create the shared protobuf descriptor registry."""
    return DescriptorRegistry()


@Pod(name="grpc_health_servicer")
def grpc_health_servicer() -> health.aio.HealthServicer:
    """Create the servicer backing the standard health checking service.

    Applications inject this Pod to report their own serving status, for
    example flipping a service to ``NOT_SERVING`` while a dependency is down.
    """
    return health.aio.HealthServicer()


@Pod(name="grpc_server_spec")
def grpc_server_spec(
    config: GrpcConfig,
    descriptor_registry: DescriptorRegistry,
    grpc_health_servicer: health.aio.HealthServicer,
) -> GrpcServerSpec:
    """Create the shared gRPC server spec from plugin configuration.

    Args:
        config: Plugin configuration.
        descriptor_registry: Registry the standard services publish into.
        grpc_health_servicer: Servicer holding the reported serving statuses.

    Returns:
        The spec collecting everything the server is built from.
    """
    spec = GrpcServerSpec(options=config.server_options)
    credentials = build_server_credentials(config)
    for address in config.bind_addresses:
        if credentials is None:
            spec.add_insecure_port(address)
        else:
            spec.add_secure_port(address, credentials)
    if config.health_service_enabled:
        enable_health_service(spec, descriptor_registry, grpc_health_servicer)
    if config.reflection_service_enabled:
        enable_reflection_service(spec, descriptor_registry)
    return spec
