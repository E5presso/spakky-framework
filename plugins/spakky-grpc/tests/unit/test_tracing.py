"""Unit tests for TracingInterceptor."""

import re
from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio

from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


def _make_handler(
    behavior: object,
) -> grpc.RpcMethodHandler:
    """Create a unary-unary RpcMethodHandler wrapping a behavior callable."""
    return grpc.unary_unary_rpc_method_handler(behavior)


def _make_call_details(
    method: str = "/test.Service/Method",
    metadata: list[tuple[str, str]] | None = None,
) -> grpc.HandlerCallDetails:
    """Create a mock HandlerCallDetails with optional metadata."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = method
    details.invocation_metadata = metadata or []
    return details


async def test_tracing_interceptor_creates_child_span_from_traceparent() -> None:
    """TracingInterceptor should create a child span when traceparent is present."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)
    captured_ctx: TraceContext | None = None

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        nonlocal captured_ctx
        captured_ctx = TraceContext.get()
        return b"response"

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details(
        metadata=[("traceparent", SAMPLE_TRACEPARENT)],
    )
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)

    assert captured_ctx is not None
    assert captured_ctx.trace_id == SAMPLE_TRACE_ID
    assert captured_ctx.parent_span_id == SAMPLE_SPAN_ID
    assert captured_ctx.span_id != SAMPLE_SPAN_ID


async def test_tracing_interceptor_creates_new_root_without_traceparent() -> None:
    """TracingInterceptor should create a new root trace when no traceparent."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)
    captured_ctx: TraceContext | None = None

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        nonlocal captured_ctx
        captured_ctx = TraceContext.get()
        return b"response"

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details(metadata=[])
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)

    assert captured_ctx is not None
    assert captured_ctx.parent_span_id is None
    traceparent = captured_ctx.to_traceparent()
    assert TRACEPARENT_PATTERN.match(traceparent)


async def test_tracing_interceptor_clears_context_after_request() -> None:
    """TracingInterceptor should clear TraceContext after RPC completes."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        assert TraceContext.get() is not None
        return b"response"

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details(
        metadata=[("traceparent", SAMPLE_TRACEPARENT)],
    )
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)

    assert TraceContext.get() is None


async def test_tracing_interceptor_clears_context_on_error() -> None:
    """TracingInterceptor should clear TraceContext even when RPC raises."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        raise RuntimeError("test error")

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details(
        metadata=[("traceparent", SAMPLE_TRACEPARENT)],
    )
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    try:
        await wrapped.unary_unary(b"request", context)
    except RuntimeError:
        pass

    assert TraceContext.get() is None


async def test_tracing_interceptor_returns_none_for_unserviced_rpc() -> None:
    """TracingInterceptor should pass through None for unserviced RPCs."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        return None

    call_details = _make_call_details()
    result = await interceptor.intercept_service(continuation, call_details)
    assert result is None


async def test_tracing_interceptor_with_invalid_traceparent_creates_new_root() -> None:
    """TracingInterceptor should create new root on invalid traceparent."""
    propagator = W3CTracePropagator()
    interceptor = TracingInterceptor(propagator=propagator)
    captured_ctx: TraceContext | None = None

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        nonlocal captured_ctx
        captured_ctx = TraceContext.get()
        return b"response"

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details(
        metadata=[("traceparent", "invalid-header")],
    )
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)

    assert captured_ctx is not None
    assert captured_ctx.parent_span_id is None
