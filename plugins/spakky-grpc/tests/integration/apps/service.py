from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import InternalError, InvalidArgument
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController
from spakky.tracing.context import TraceContext


@dataclass
class HelloRequest:
    """Request message for integration scenarios."""

    name: Annotated[str, ProtoField(number=1)]


@dataclass
class HelloReply:
    """Response message for greeting scenarios."""

    message: Annotated[str, ProtoField(number=1)]


@dataclass
class NamesReply:
    """Response message for aggregated streaming requests."""

    summary: Annotated[str, ProtoField(number=1)]


@dataclass
class TraceSnapshotReply:
    """Response carrying the trace context observed in the controller."""

    trace_id: Annotated[str, ProtoField(number=1)]
    span_id: Annotated[str, ProtoField(number=2)]
    parent_span_id: Annotated[str, ProtoField(number=3)]


@GrpcController(package="integration.v1", service_name="IntegrationService")
class IntegrationServiceController:
    """Test gRPC controller covering unary, streaming, and interceptors."""

    @rpc()
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        """Return a unary greeting."""
        return HelloReply(message=f"Hello, {request.name}!")

    @rpc(method_type=RpcMethodType.SERVER_STREAMING, response_type=HelloReply)
    async def stream_hello(
        self, request: HelloRequest
    ) -> AsyncGenerator[HelloReply, None]:
        """Emit multiple greetings for a single request."""
        yield HelloReply(message=f"Hello, {request.name}!")
        yield HelloReply(message=f"Goodbye, {request.name}!")

    @rpc(
        method_type=RpcMethodType.CLIENT_STREAMING,
        request_type=HelloRequest,
        response_type=NamesReply,
    )
    async def collect_names(
        self, request_iterator: AsyncIterator[HelloRequest]
    ) -> NamesReply:
        """Aggregate a stream of names into one response."""
        names: list[str] = []
        async for request in request_iterator:
            names.append(request.name)
        return NamesReply(summary=",".join(names))

    @rpc(
        method_type=RpcMethodType.BIDI_STREAMING,
        request_type=HelloRequest,
        response_type=HelloReply,
    )
    async def echo_names(
        self, request_iterator: AsyncIterator[HelloRequest]
    ) -> AsyncGenerator[HelloReply, None]:
        """Echo each streamed request as an uppercase greeting."""
        async for request in request_iterator:
            yield HelloReply(message=request.name.upper())

    @rpc()
    async def fail_invalid_argument(self, request: HelloRequest) -> HelloReply:
        """Raise a managed gRPC error for interceptor validation."""
        raise InvalidArgument()

    @rpc()
    async def capture_trace(self, request: HelloRequest) -> TraceSnapshotReply:
        """Return the active trace context seen in the controller."""
        trace_context = TraceContext.get()
        if trace_context is None:
            raise InternalError()
        return TraceSnapshotReply(
            trace_id=trace_context.trace_id,
            span_id=trace_context.span_id,
            parent_span_id=trace_context.parent_span_id or "",
        )
