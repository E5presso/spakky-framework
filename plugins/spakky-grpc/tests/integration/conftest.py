"""Integration test fixtures for gRPC end-to-end behaviors."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from unittest.mock import MagicMock

import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import NotFound
from spakky.plugins.grpc.handler import GrpcServiceHandler
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator
from typing_extensions import override


@dataclass
class EchoRequest:
    """Unary and bidi request payload."""

    message: Annotated[str, ProtoField(number=1)]


@dataclass
class EchoReply:
    """Unary and streaming response payload."""

    message: Annotated[str, ProtoField(number=1)]


@dataclass
class CountRequest:
    """Server-streaming request payload."""

    count: Annotated[int, ProtoField(number=1)]


@dataclass
class NumberChunk:
    """Client-streaming request payload."""

    value: Annotated[int, ProtoField(number=1)]


@dataclass
class SumReply:
    """Client-streaming aggregate response payload."""

    total: Annotated[int, ProtoField(number=1)]


@dataclass
class FailRequest:
    """Request payload for error-path testing."""

    resource_id: Annotated[str, ProtoField(number=1)]


@GrpcController(package="itest.v1", service_name="IntegrationService")
class IntegrationController:
    """Controller exposing all gRPC method shapes."""

    @rpc(
        method_type=RpcMethodType.UNARY,
        request_type=EchoRequest,
        response_type=EchoReply,
    )
    async def unary_echo(self, request: EchoRequest) -> EchoReply:
        """Return the same message for unary requests."""
        return EchoReply(message=request.message)

    @rpc(
        method_type=RpcMethodType.SERVER_STREAMING,
        request_type=CountRequest,
        response_type=EchoReply,
    )
    async def stream_count(self, request: CountRequest) -> AsyncIterator[EchoReply]:
        """Yield count-prefixed messages as a server stream."""
        for idx in range(request.count):
            yield EchoReply(message=f"item-{idx}")

    @rpc(
        method_type=RpcMethodType.CLIENT_STREAMING,
        request_type=NumberChunk,
        response_type=SumReply,
    )
    async def sum_stream(self, request: AsyncIterator[NumberChunk]) -> SumReply:
        """Aggregate client stream values into a single response."""
        total = 0
        async for item in request:
            total += item.value
        return SumReply(total=total)

    @rpc(
        method_type=RpcMethodType.BIDI_STREAMING,
        request_type=EchoRequest,
        response_type=EchoReply,
    )
    async def chat(
        self, request: AsyncIterator[EchoRequest]
    ) -> AsyncIterator[EchoReply]:
        """Echo each inbound message as a bidi stream."""
        async for item in request:
            yield EchoReply(message=f"echo:{item.message}")

    @rpc(
        method_type=RpcMethodType.UNARY,
        request_type=FailRequest,
        response_type=EchoReply,
    )
    async def fail_not_found(self, request: FailRequest) -> EchoReply:
        """Always fail with a mapped gRPC status error."""
        raise NotFound()


class FakeTracePropagator(ITracePropagator):
    """Simple propagator that records extract/inject interactions."""

    def __init__(self) -> None:
        self.extract_calls: list[dict[str, str]] = []
        self.inject_calls: list[dict[str, str]] = []

    @override
    def inject(self, carrier: dict[str, str]) -> None:
        """Inject active trace context into the outbound carrier."""
        self.inject_calls.append(carrier)
        current = TraceContext.get()
        if current is not None:
            carrier["traceparent"] = current.to_traceparent()

    @override
    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Extract trace context from inbound metadata."""
        self.extract_calls.append(carrier)
        traceparent = carrier.get("traceparent")
        if traceparent is None:
            return None
        return TraceContext.from_traceparent(traceparent)

    @override
    def fields(self) -> list[str]:
        """Return the supported propagation field names."""
        return ["traceparent", "tracestate"]


@pytest.fixture
def application_context() -> MagicMock:
    """Application context mock used by handler dispatch."""
    context = MagicMock(spec=IApplicationContext)
    context.clear_context = MagicMock()
    return context


@pytest.fixture
def registry() -> DescriptorRegistry:
    """Descriptor registry populated with integration controller schema."""
    descriptor_registry = DescriptorRegistry()
    descriptor_registry.register(build_file_descriptor(IntegrationController))
    return descriptor_registry


@pytest.fixture
def container() -> MagicMock:
    """Container mock returning a fresh controller instance."""
    container_mock = MagicMock(spec=IContainer)
    container_mock.get = MagicMock(side_effect=lambda type_, name=None: type_())
    return container_mock


@pytest.fixture
def propagator() -> FakeTracePropagator:
    """Tracing propagator used by interceptor integration tests."""
    return FakeTracePropagator()


@pytest.fixture
async def grpc_server(
    application_context: MagicMock,
    container: MagicMock,
    propagator: FakeTracePropagator,
    registry: DescriptorRegistry,
) -> AsyncIterator[tuple[grpc.aio.Server, str]]:
    """Start a real gRPC server with generic handler and interceptors."""
    TraceContext.clear()
    handler = GrpcServiceHandler(
        controller_type=IntegrationController,
        package="itest.v1",
        service_name="IntegrationService",
        container=container,
        application_context=application_context,
        registry=registry,
    )
    server = grpc.aio.server(
        interceptors=[
            ErrorHandlingInterceptor(),
            TracingInterceptor(propagator=propagator),
        ]
    )
    server.add_generic_rpc_handlers([handler])
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield server, f"127.0.0.1:{port}"
    finally:
        await server.stop(grace=0)
        TraceContext.clear()


@pytest.fixture
async def grpc_channel(
    grpc_server: tuple[grpc.aio.Server, str],
) -> AsyncIterator[grpc.aio.Channel]:
    """Create a connected gRPC channel for test calls."""
    _server, address = grpc_server
    channel = grpc.aio.insecure_channel(address)
    try:
        yield channel
    finally:
        await channel.close()


@pytest.fixture
def message_types(registry: DescriptorRegistry) -> dict[str, type]:
    """Resolve runtime protobuf message classes from descriptor registry."""
    return {
        "EchoRequest": registry.get_message_class("itest.v1.EchoRequest"),
        "EchoReply": registry.get_message_class("itest.v1.EchoReply"),
        "CountRequest": registry.get_message_class("itest.v1.CountRequest"),
        "NumberChunk": registry.get_message_class("itest.v1.NumberChunk"),
        "SumReply": registry.get_message_class("itest.v1.SumReply"),
        "FailRequest": registry.get_message_class("itest.v1.FailRequest"),
    }
