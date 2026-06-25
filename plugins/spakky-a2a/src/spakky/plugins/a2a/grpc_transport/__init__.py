"""gRPC transport bindings for the official A2A service descriptor."""

from spakky.plugins.a2a.grpc_transport.builder import build_a2a_grpc_handler
from spakky.plugins.a2a.grpc_transport.handler import (
    A2A_GRPC_SERVICE,
    A2AGrpcHandler,
)

__all__ = [
    "A2A_GRPC_SERVICE",
    "A2AGrpcHandler",
    "build_a2a_grpc_handler",
]
