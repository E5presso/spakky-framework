"""Echo controller used as fixture for gRPC integration tests.

Exposes all four RPC streaming patterns plus an error-dispatching endpoint
used to exercise ``ErrorHandlingInterceptor`` mappings.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, ClassVar

from spakky.tracing.context import TraceContext

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import (
    AlreadyExists,
    FailedPrecondition,
    InternalError,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    Unauthenticated,
    Unavailable,
)
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class EchoRequest:
    """Single-field request used by unary and streaming echo methods."""

    text: Annotated[str, ProtoField(number=1)]


@dataclass
class EchoReply:
    """Single-field reply mirroring the request text."""

    text: Annotated[str, ProtoField(number=1)]


@dataclass
class CountRequest:
    """Controls how many messages the server should emit/aggregate."""

    count: Annotated[int, ProtoField(number=1)]


@dataclass
class CountReply:
    """Aggregated count reply for client-streaming tests."""

    total: Annotated[int, ProtoField(number=1)]


@dataclass
class ErrorRequest:
    """Identifies which error the controller should raise."""

    code: Annotated[str, ProtoField(number=1)]


@dataclass
class TraceReply:
    """Returns the captured server-side trace context."""

    trace_id: Annotated[str, ProtoField(number=1)]
    parent_span_id: Annotated[str, ProtoField(number=2)]


# Maps client-provided codes to the gRPC status errors to raise.
ERROR_CODE_MAP: dict[str, type[Exception]] = {
    "invalid_argument": InvalidArgument,
    "not_found": NotFound,
    "already_exists": AlreadyExists,
    "permission_denied": PermissionDenied,
    "unauthenticated": Unauthenticated,
    "failed_precondition": FailedPrecondition,
    "unavailable": Unavailable,
    "internal": InternalError,
}


class UnexpectedTestError(Exception):
    """Plain exception raised to exercise the INTERNAL fallback branch."""

    ...


@GrpcController(package="test.echo")
class EchoController:
    """Echo service covering every RPC pattern plus error/tracing hooks."""

    TRACE_MISSING: ClassVar[str] = "__missing__"
    """Placeholder returned when no ``TraceContext`` is active."""

    @rpc()
    async def unary_echo(self, request: EchoRequest) -> EchoReply:
        """Return the request text unchanged."""
        return EchoReply(text=request.text)

    @rpc(
        method_type=RpcMethodType.SERVER_STREAMING,
        request_type=CountRequest,
        response_type=EchoReply,
    )
    async def server_streaming_count(
        self, request: CountRequest
    ) -> AsyncIterator[EchoReply]:
        """Yield ``count`` replies numbered from 0."""
        for index in range(request.count):
            yield EchoReply(text=f"item-{index}")

    @rpc(
        method_type=RpcMethodType.CLIENT_STREAMING,
        request_type=CountRequest,
        response_type=CountReply,
    )
    async def client_streaming_sum(
        self, requests: AsyncIterator[CountRequest]
    ) -> CountReply:
        """Sum every inbound ``count`` field into a single reply."""
        total = 0
        async for item in requests:
            total += item.count
        return CountReply(total=total)

    @rpc(
        method_type=RpcMethodType.BIDI_STREAMING,
        request_type=EchoRequest,
        response_type=EchoReply,
    )
    async def bidi_streaming_echo(
        self, requests: AsyncIterator[EchoRequest]
    ) -> AsyncIterator[EchoReply]:
        """Echo every inbound request back to the client."""
        async for item in requests:
            yield EchoReply(text=item.text)

    @rpc()
    async def raise_error(self, request: ErrorRequest) -> EchoReply:
        """Raise the gRPC error identified by ``request.code``.

        Unknown codes raise :class:`UnexpectedTestError` to exercise the
        generic INTERNAL fallback path.
        """
        error_type = ERROR_CODE_MAP.get(request.code)
        if error_type is None:
            raise UnexpectedTestError(request.code)
        raise error_type

    @rpc()
    async def capture_trace(self, request: EchoRequest) -> TraceReply:
        """Return the active ``TraceContext`` so tests can verify propagation."""
        del request
        ctx = TraceContext.get()
        if ctx is None:
            return TraceReply(
                trace_id=self.TRACE_MISSING,
                parent_span_id=self.TRACE_MISSING,
            )
        return TraceReply(
            trace_id=ctx.trace_id,
            parent_span_id=ctx.parent_span_id or "",
        )
