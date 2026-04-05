"""Unit tests for ErrorHandlingInterceptor."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio
import pytest

from spakky.plugins.grpc.error import InternalError, InvalidArgument, NotFound
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor


def _make_handler(
    *,
    unary_unary: AsyncMock | None = None,
    unary_stream: AsyncMock | None = None,
    stream_unary: AsyncMock | None = None,
    stream_stream: AsyncMock | None = None,
) -> MagicMock:
    """Create a mock RpcMethodHandler with the given behavior methods."""
    handler = MagicMock(spec=grpc.RpcMethodHandler)
    handler.request_streaming = stream_unary is not None or stream_stream is not None
    handler.response_streaming = unary_stream is not None or stream_stream is not None
    handler.request_deserializer = None
    handler.response_serializer = None
    handler.unary_unary = unary_unary
    handler.unary_stream = unary_stream
    handler.stream_unary = stream_unary
    handler.stream_stream = stream_stream
    return handler


def _make_call_details(method: str = "/test.Service/Method") -> MagicMock:
    """Create a mock HandlerCallDetails."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = method
    details.invocation_metadata = ()
    return details


@pytest.fixture
def interceptor() -> ErrorHandlingInterceptor:
    """Create an ErrorHandlingInterceptor with debug=False."""
    return ErrorHandlingInterceptor()


@pytest.fixture
def debug_interceptor() -> ErrorHandlingInterceptor:
    """Create an ErrorHandlingInterceptor with debug=True."""
    return ErrorHandlingInterceptor(debug=True)


@pytest.fixture
def context() -> AsyncMock:
    """Create a mock gRPC ServicerContext."""
    ctx = AsyncMock(spec=grpc.aio.ServicerContext)
    ctx.abort = AsyncMock(side_effect=grpc.aio.AbortError(grpc.StatusCode.INTERNAL, ""))
    return ctx


async def test_unary_handler_passes_through_on_success(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """Successful unary handler should pass through unchanged."""
    behavior = AsyncMock(return_value=b"response")
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    result = await wrapped.unary_unary(b"request", context)

    assert result == b"response"
    behavior.assert_awaited_once_with(b"request", context)


async def test_unary_handler_catches_grpc_error_expect_abort_with_status(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """AbstractSpakkyGRPCError should be converted to the declared gRPC status."""
    behavior = AsyncMock(side_effect=NotFound())
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    with pytest.raises(grpc.aio.AbortError):
        await wrapped.unary_unary(b"request", context)

    context.abort.assert_awaited_once_with(grpc.StatusCode.NOT_FOUND, "Not Found")


async def test_unary_handler_catches_unexpected_error_expect_internal(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """Unhandled Exception should be mapped to INTERNAL status."""
    behavior = AsyncMock(side_effect=RuntimeError("oops"))
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    with pytest.raises(grpc.aio.AbortError):
        await wrapped.unary_unary(b"request", context)

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INTERNAL, InternalError.message
    )


async def test_unary_handler_reraises_grpc_rpc_error(
    interceptor: ErrorHandlingInterceptor,
) -> None:
    """gRPC RpcError from the handler should be re-raised, not converted."""
    rpc_error = grpc.aio.AbortError(grpc.StatusCode.CANCELLED, "cancelled")
    behavior = AsyncMock(side_effect=rpc_error)
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    ctx = AsyncMock(spec=grpc.aio.ServicerContext)
    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    with pytest.raises(grpc.aio.AbortError):
        await wrapped.unary_unary(b"request", ctx)

    ctx.abort.assert_not_awaited()


async def test_unary_handler_debug_mode_includes_traceback(
    debug_interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """In debug mode, INTERNAL errors should include the traceback."""
    behavior = AsyncMock(side_effect=RuntimeError("oops"))
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await debug_interceptor.intercept_service(
        continuation, _make_call_details()
    )
    assert wrapped.unary_unary is not None
    with pytest.raises(grpc.aio.AbortError):
        await wrapped.unary_unary(b"request", context)

    _code, details = context.abort.call_args.args
    assert "RuntimeError" in details
    assert "Traceback" in details


async def test_unary_handler_logs_unexpected_error(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled exceptions should be logged at ERROR level."""
    behavior = AsyncMock(side_effect=RuntimeError("oops"))
    handler = _make_handler(unary_unary=behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_unary is not None
    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(grpc.aio.AbortError),
    ):
        await wrapped.unary_unary(b"request", context)

    assert "RuntimeError('oops')" in caplog.text


async def test_intercept_service_returns_none_for_none_handler(
    interceptor: ErrorHandlingInterceptor,
) -> None:
    """When continuation returns None, interceptor should return None."""
    continuation = AsyncMock(return_value=None)
    result = await interceptor.intercept_service(continuation, _make_call_details())
    assert result is None


async def test_stream_handler_passes_through_on_success(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """Successful streaming handler should yield all responses."""

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


async def test_stream_handler_catches_grpc_error_expect_abort(
    interceptor: ErrorHandlingInterceptor,
    context: AsyncMock,
) -> None:
    """AbstractSpakkyGRPCError in a streaming handler should trigger abort."""

    async def stream_behavior(
        request: object, ctx: grpc.aio.ServicerContext
    ) -> AsyncIterator[bytes]:
        yield b"first"
        raise InvalidArgument()

    handler = _make_handler(unary_stream=stream_behavior)
    continuation = AsyncMock(return_value=handler)

    wrapped = await interceptor.intercept_service(continuation, _make_call_details())
    assert wrapped.unary_stream is not None
    with pytest.raises(grpc.aio.AbortError):
        async for _ in wrapped.unary_stream(b"request", context):  # type: ignore[arg-type] — grpc stubs declare sync Iterator but grpc.aio uses async
            pass

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INVALID_ARGUMENT, "Invalid Argument"
    )


async def test_multiple_error_types_map_to_correct_status(
    interceptor: ErrorHandlingInterceptor,
) -> None:
    """Different error subclasses should map to their respective status codes."""
    for error_class in [NotFound, InvalidArgument]:
        behavior = AsyncMock(side_effect=error_class())
        handler = _make_handler(unary_unary=behavior)
        continuation = AsyncMock(return_value=handler)

        ctx = AsyncMock(spec=grpc.aio.ServicerContext)
        ctx.abort = AsyncMock(
            side_effect=grpc.aio.AbortError(error_class.status_code, "")
        )

        wrapped = await interceptor.intercept_service(
            continuation, _make_call_details()
        )
        assert wrapped.unary_unary is not None
        with pytest.raises(grpc.aio.AbortError):
            await wrapped.unary_unary(b"request", ctx)

        ctx.abort.assert_awaited_once_with(error_class.status_code, error_class.message)
