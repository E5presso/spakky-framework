"""gRPC plugin for Spakky framework.

This plugin provides code-first gRPC service integration with:
- @GrpcController stereotype for declaring gRPC services
- @rpc decorator for defining RPC methods with streaming support
- ProtoField annotation for protobuf field number mapping
"""

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-grpc")
"""Plugin identifier for the gRPC integration."""
