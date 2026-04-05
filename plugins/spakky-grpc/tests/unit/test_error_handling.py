"""Unit tests for ErrorHandlingInterceptor."""

from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio

from spakky.plugins.grpc.error import InvalidArgument, NotFound
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor


def _make_handler(
    behavior: object,
) -> grpc.RpcMethodHandler:
    """Create a unary-unary RpcMethodHandler wrapping a behavior callable."""
    return grpc.unary_unary_rpc_method_handler(behavior)


def _make_call_details(
    method: str = "/test.Service/Method",
) -> grpc.HandlerCallDetails:
    """Create a mock HandlerCallDetails."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = method
    details.invocation_metadata = []
    return details


async def test_error_handling_interceptor_passes_through_on_success() -> None:
    """ErrorHandlingInterceptor should pass through on successful RPC."""
    interceptor = ErrorHandlingInterceptor()
    expected_response = b"response"

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> bytes:
        return expected_response

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details()
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    result = await wrapped.unary_unary(b"request", context)
    assert result == expected_response
    context.abort.assert_not_called()


async def test_error_handling_interceptor_converts_grpc_error_to_status() -> None:
    """ErrorHandlingInterceptor should convert AbstractSpakkyGRPCError to gRPC status."""
    interceptor = ErrorHandlingInterceptor()

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> None:
        raise NotFound()

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details()
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)
    context.abort.assert_awaited_once_with(grpc.StatusCode.NOT_FOUND, "Not Found")


async def test_error_handling_interceptor_converts_invalid_argument() -> None:
    """ErrorHandlingInterceptor should convert InvalidArgument to INVALID_ARGUMENT status."""
    interceptor = ErrorHandlingInterceptor()

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> None:
        raise InvalidArgument()

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details()
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)
    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INVALID_ARGUMENT, "Invalid Argument"
    )


async def test_error_handling_interceptor_converts_unhandled_to_internal() -> None:
    """ErrorHandlingInterceptor should convert unhandled exceptions to INTERNAL status."""
    interceptor = ErrorHandlingInterceptor()

    async def behavior(
        request: object, context: grpc.aio.ServicerContext
    ) -> None:
        raise RuntimeError("unexpected error")

    handler = _make_handler(behavior)

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        return handler

    call_details = _make_call_details()
    wrapped = await interceptor.intercept_service(continuation, call_details)

    context = AsyncMock(spec=grpc.aio.ServicerContext)
    await wrapped.unary_unary(b"request", context)
    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INTERNAL, "Internal Server Error"
    )


async def test_error_handling_interceptor_returns_none_for_unserviced_rpc() -> None:
    """ErrorHandlingInterceptor should pass through None for unserviced RPCs."""
    interceptor = ErrorHandlingInterceptor()

    async def continuation(
        details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        return None

    call_details = _make_call_details()
    result = await interceptor.intercept_service(continuation, call_details)
    assert result is None
