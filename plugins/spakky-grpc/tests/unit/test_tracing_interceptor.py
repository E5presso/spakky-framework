"""Unit tests for TracingInterceptor."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio
import pytest

from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor


class FakePropagator(ITracePropagator):
    """Minimal propagator for testing that stores extract/inject calls."""

    def __init__(self, *, extract_result: TraceContext | None = None) -> None:
        self._extract_result = extract_result
        self.extract_calls: list[dict[str, str]] = []
        self.inject_calls: list[dict[str, str]] = []

    def inject(self, carrier: dict[str, str]) -> None:
        """Copy the ambient trace context into the carrier."""
        self.inject_calls.append(carrier)
        ctx = TraceContext.get()
        if ctx is not None:
            carrier["traceparent"] = ctx.to_traceparent()

    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Return the configured extract result."""
        self.extract_calls.append(carrier)
        return self._extract_result

    def fields(self) -> list[str]:
        """Return W3C trace context field names."""
        return ["traceparent", "tracestate"]


def _make_handler(
    *,
    unary_unary: AsyncMock | None = None,
    unary_stream: object | None = None,
) -> MagicMock:
    """Create a mock RpcMethodHandler."""
    handler = MagicMock(spec=grpc.RpcMethodHandler)
    handler.request_streaming = False
    handler.response_streaming = unary_stream is not None
    handler.request_deserializer = None
    handler.response_serializer = None
    handler.unary_unary = unary_unary
    handler.unary_stream = unary_stream
    handler.stream_unary = None
    handler.stream_stream = None
    return handler


def _make_call_details(
    method: str = "/test.Service/Method",
    metadata: tuple[tuple[str, str | bytes], ...] | None = (),
) -> MagicMock:
    """Create a mock HandlerCallDetails with optional metadata."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = method
    details.invocation_metadata = metadata
    return details


@pytest.fixture(autouse=True)
def _clear_trace_context() -> None:
    """Ensure trace context is clean before each test."""
    TraceContext.clear()


@pytest.fixture
def context() -> AsyncMock:
    """Create a mock gRPC ServicerContext."""
    ctx = AsyncMock(spec=grpc.aio.ServicerContext)
    return ctx


async def test_tracing_interceptor_creates_new_root_when_no_parent(
    context: AsyncMock,
) -> None:
    """When no traceparent exists, a new root trace should be created."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert len(propagator.extract_calls) == 1
    assert len(propagator.inject_calls) == 1
    assert "traceparent" in propagator.inject_calls[0]


async def test_tracing_interceptor_creates_child_when_parent_exists(
    context: AsyncMock,
) -> None:
    """When traceparent exists in metadata, a child span should be created."""
    parent = TraceContext.new_root()
    propagator = FakePropagator(extract_result=parent)
    interceptor = TracingInterceptor(propagator=propagator)

    captured_ctx: list[TraceContext | None] = []

    async def capture_behavior(request: object, ctx: grpc.aio.ServicerContext) -> bytes:
        captured_ctx.append(TraceContext.get())
        return b"ok"

    handler = _make_handler(unary_unary=AsyncMock(side_effect=capture_behavior))
    continuation = AsyncMock(return_value=handler)

    metadata = (("traceparent", parent.to_traceparent()),)
    wrapped = await interceptor.intercept_service(
        continuation, _make_call_details(metadata=metadata)
    )
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert len(captured_ctx) == 1
    child = captured_ctx[0]
    assert child is not None
    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.parent_span_id == parent.span_id


async def test_tracing_interceptor_extracts_metadata_as_dict(
    context: AsyncMock,
) -> None:
    """Invocation metadata should be converted to a dict for the propagator."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    metadata = (("traceparent", "00-abc-def-01"), ("custom-key", "custom-value"))
    wrapped = await interceptor.intercept_service(
        continuation, _make_call_details(metadata=metadata)
    )
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert propagator.extract_calls[0] == {
        "traceparent": "00-abc-def-01",
        "custom-key": "custom-value",
    }


async def test_tracing_interceptor_handles_binary_metadata_values(
    context: AsyncMock,
) -> None:
    """Binary metadata values (bytes) should be decoded to str."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    metadata = (("key", b"bytes-value"),)
    wrapped = await interceptor.intercept_service(
        continuation, _make_call_details(metadata=metadata)
    )
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert propagator.extract_calls[0] == {"key": "bytes-value"}


async def test_tracing_interceptor_injects_trailing_metadata(
    context: AsyncMock,
) -> None:
    """Trace context should be injected into trailing metadata."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    context.set_trailing_metadata.assert_called_once()
    trailing = dict(context.set_trailing_metadata.call_args.args[0])
    assert "traceparent" in trailing


async def test_tracing_interceptor_clears_context_after_rpc(
    context: AsyncMock,
) -> None:
    """Trace context should be cleared after the RPC completes."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert TraceContext.get() is None


async def test_tracing_interceptor_clears_context_on_error(
    context: AsyncMock,
) -> None:
    """Trace context should be cleared even if the handler raises."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(side_effect=RuntimeError("boom"))
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    with pytest.raises(RuntimeError, match="boom"):
        await wrapped.unary_unary(b"request", context)

    assert TraceContext.get() is None


async def test_tracing_interceptor_returns_none_for_none_handler() -> None:
    """When continuation returns None, interceptor should return None."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    continuation = AsyncMock(return_value=None)

    result = await interceptor.intercept_service(continuation, _make_call_details())
    assert result is None
    assert TraceContext.get() is None


async def test_tracing_interceptor_handles_none_metadata(
    context: AsyncMock,
) -> None:
    """None invocation_metadata should be handled gracefully."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    behavior = AsyncMock(return_value=b"ok")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(
        continuation, _make_call_details(metadata=None)
    )
    assert wrapped.unary_unary is not None
    await wrapped.unary_unary(b"request", context)

    assert propagator.extract_calls[0] == {}


async def test_tracing_interceptor_stream_handler_injects_and_clears(
    context: AsyncMock,
) -> None:
    """Streaming handler should inject trailing metadata and clear context."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)

    async def stream_behavior(
        request: object, ctx: grpc.aio.ServicerContext
    ) -> AsyncIterator[bytes]:
        yield b"a"
        yield b"b"

    handler = _make_handler(unary_stream=stream_behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_stream is not None
    results = [item async for item in wrapped.unary_stream(b"request", context)]  # type: ignore[arg-type] — grpc stubs declare sync Iterator but grpc.aio uses async

    assert results == [b"a", b"b"]
    context.set_trailing_metadata.assert_called_once()
    assert TraceContext.get() is None


async def test_tracing_interceptor_clears_context_on_continuation_failure() -> None:
    """Trace context should be cleared if continuation raises an exception."""
    propagator = FakePropagator(extract_result=None)
    interceptor = TracingInterceptor(propagator=propagator)
    continuation = AsyncMock(side_effect=RuntimeError("continuation failed"))

    with pytest.raises(RuntimeError, match="continuation failed"):
        await interceptor.intercept_service(continuation, _make_call_details())

    assert TraceContext.get() is None
