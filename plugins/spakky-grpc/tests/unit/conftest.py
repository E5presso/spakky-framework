"""Shared fixtures for gRPC PostProcessor and handler tests."""

from dataclasses import dataclass
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class HelloRequest:
    """Test request message."""

    name: Annotated[str, ProtoField(number=1)]


@dataclass
class HelloReply:
    """Test response message."""

    message: Annotated[str, ProtoField(number=1)]


@GrpcController(package="test.v1")
class GreeterController:
    """Test gRPC controller."""

    @rpc()
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        """Simple unary RPC."""
        return HelloReply(message=f"Hello {request.name}")


@pytest.fixture
def container() -> MagicMock:
    """Create a mock IContainer."""
    return MagicMock(spec=IContainer)


@pytest.fixture
def application_context() -> MagicMock:
    """Create a mock IApplicationContext."""
    ctx = MagicMock(spec=IApplicationContext)
    ctx.get_or_none = MagicMock(return_value=None)
    return ctx


@pytest.fixture
def registry() -> DescriptorRegistry:
    """Create a fresh DescriptorRegistry."""
    return DescriptorRegistry()


@pytest.fixture
def server() -> AsyncMock:
    """Create a mock grpc.aio.Server."""
    mock = AsyncMock(spec=grpc.aio.Server)
    mock.add_generic_rpc_handlers = MagicMock()
    return mock
