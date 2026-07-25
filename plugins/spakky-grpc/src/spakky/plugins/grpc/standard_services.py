"""Standard gRPC services exposed alongside the application's own services.

Two services come from the gRPC ecosystem rather than from user code:

- ``grpc.health.v1.Health`` is what Kubernetes' native gRPC probe calls, so a
  gRPC-only deployment has no other way to report liveness.
- Server reflection is the only way to discover what a running server exposes
  when the schema is built at runtime from pydantic models and no ``.proto``
  artifact is ever produced.

Both are attached through :meth:`GrpcServerSpec.add_service_registrar`,
because their servicers need the concrete ``grpc.aio.Server`` that only
exists once the spec is built on the serving event loop.
"""

from google.protobuf.descriptor import FileDescriptor
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection, reflection_pb2

import grpc.aio
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec


def enable_health_service(
    spec: GrpcServerSpec,
    registry: DescriptorRegistry,
    servicer: health.aio.HealthServicer,
) -> None:
    """Expose the standard health checking service on the server.

    Every registered service is reported ``SERVING`` when the server comes up.
    A probe that names a service — ``grpc_health_probe -service=<name>`` or the
    Kubernetes ``grpc.service`` field — answers ``NOT_FOUND`` for any name the
    servicer has never been told about, so a healthy server would otherwise be
    judged unready. Applications flip individual services afterwards through
    the injected servicer.

    Args:
        spec: Spec collecting the deferred server configuration.
        registry: Registry the health schema is mirrored into so reflection
            can describe the service it advertises, and whose service list
            seeds the initial statuses.
        servicer: Servicer holding the reported serving statuses.
    """
    _mirror_descriptor(registry, health_pb2.DESCRIPTOR)

    async def _register(server: grpc.aio.Server) -> None:
        health_pb2_grpc.add_HealthServicer_to_server(servicer, server)
        for service_name in registry.service_names:
            await servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)

    spec.add_service_registrar(_register)


def enable_reflection_service(
    spec: GrpcServerSpec, registry: DescriptorRegistry
) -> None:
    """Expose server reflection over the code-first descriptor pool.

    Args:
        spec: Spec collecting the deferred server configuration.
        registry: Registry holding every descriptor built from controllers;
            its service list is read at build time so services registered
            later during post-processing are still advertised.
    """
    _mirror_descriptor(registry, reflection_pb2.DESCRIPTOR)

    async def _register(server: grpc.aio.Server) -> None:
        reflection.enable_server_reflection(
            registry.service_names, server, pool=registry.pool
        )

    spec.add_service_registrar(_register)


def _mirror_descriptor(
    registry: DescriptorRegistry, file_descriptor: FileDescriptor
) -> None:
    """Copy a compiled descriptor from the default pool into *registry*.

    The standard services are compiled into protobuf's default pool, while
    reflection answers from the plugin's own pool. Without this copy a client
    could list ``grpc.health.v1.Health`` but never describe it.

    Args:
        registry: Registry receiving the descriptor.
        file_descriptor: Descriptor of the standard service's proto file.
    """
    if registry.is_registered(file_descriptor.name):
        return
    file_proto = FileDescriptorProto()
    file_descriptor.CopyToProto(file_proto)
    registry.register(file_proto)
