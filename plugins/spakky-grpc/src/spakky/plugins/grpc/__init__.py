"""gRPC plugin for Spakky framework.

This plugin provides code-first gRPC service integration with:
- @GrpcController stereotype for declaring gRPC services
- @rpc decorator for defining RPC methods with streaming support
- ProtoField annotation for protobuf field number mapping
"""

from spakky.core.application.plugin import Plugin
from spakky.plugins.grpc.config import (
    SPAKKY_GRPC_CONFIG_ENV_PREFIX,
    GrpcConfig,
)

PLUGIN_NAME = Plugin(name="spakky-grpc")
"""Plugin identifier for the gRPC integration."""

__all__ = [
    "PLUGIN_NAME",
    "SPAKKY_GRPC_CONFIG_ENV_PREFIX",
    "GrpcConfig",
]
