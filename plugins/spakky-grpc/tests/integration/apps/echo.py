"""Echo controller used as fixture for gRPC integration tests.

Exposes all four RPC streaming patterns plus an error-dispatching endpoint
used to exercise ``ErrorHandlingInterceptor`` mappings.
"""

from collections.abc import AsyncIterator
from typing import Annotated, ClassVar

from pydantic import BaseModel
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


class EchoRequest(BaseModel):
    """Single-field request used by unary and streaming echo methods.

    Declared without ``ProtoField`` — the field number is derived from the
    field name hash (zero-config code-first protobuf).
    """

    text: str


class EchoReply(BaseModel):
    """Single-field reply mirroring the request text (zero-config numbering)."""

    text: str


class CountRequest(BaseModel):
    """Controls how many messages the server should emit/aggregate."""

    count: int


class CountReply(BaseModel):
    """Aggregated count reply for client-streaming tests."""

    total: int


class ProfileRequest(BaseModel):
    """Multi-field, mixed-type zero-config request.

    Exercises the zero-config DX path with more than one field: every field
    number is derived from the field name hash, so the client and server
    agree on the wire layout without any ``ProtoField`` annotation.
    """

    nickname: str
    age: int
    verified: bool


class ProfileReply(BaseModel):
    """Multi-field zero-config reply mirroring the request fields."""

    nickname: str
    age: int
    verified: bool


class ErrorRequest(BaseModel):
    """Identifies which error the controller should raise."""

    code: str


class TraceReply(BaseModel):
    """Returns the captured server-side trace context.

    Retains explicit ``ProtoField`` overrides so the integration suite
    keeps exercising the explicit-numbering path alongside the zero-config
    messages above.
    """

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
    async def echo_profile(self, request: ProfileRequest) -> ProfileReply:
        """Return a multi-field zero-config reply mirroring the request."""
        return ProfileReply(
            nickname=request.nickname,
            age=request.age,
            verified=request.verified,
        )

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
