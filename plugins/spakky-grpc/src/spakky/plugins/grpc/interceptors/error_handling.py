"""Error handling interceptor for gRPC servers.

Catches domain exceptions and maps them to appropriate gRPC status codes.
Unexpected exceptions are logged and returned as ``INTERNAL`` status.
"""

import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from logging import getLogger
from typing import Any

import grpc
import grpc.aio

from spakky.plugins.grpc.error import AbstractGrpcStatusError, InternalError

logger = getLogger(__name__)


class ErrorHandlingInterceptor(grpc.aio.ServerInterceptor):
    """Interceptor that converts exceptions to gRPC status codes.

    ``AbstractGrpcStatusError`` subclasses are mapped to their declared
    ``status_code``.  All other exceptions become ``INTERNAL``.

    Attributes:
        __debug: When True, include tracebacks in error details.
    """

    __debug: bool

    def __init__(self, *, debug: bool = False) -> None:
        """Initialize the error handling interceptor.

        Args:
            debug: Whether to include full tracebacks in error details.
        """
        self.__debug = debug

    def _wrap_unary_behavior(
        self,
        behavior: Callable[..., Awaitable[object]],
    ) -> Callable[..., Awaitable[object]]:
        """Wrap a unary response handler with error handling."""

        async def wrapper(
            request_or_iterator: object,
            context: grpc.aio.ServicerContext,
        ) -> object:
            try:
                return await behavior(request_or_iterator, context)
            except AbstractGrpcStatusError as error:
                await context.abort(error.status_code, error.message)
            except Exception as error:
                if isinstance(error, grpc.aio.BaseError):
                    raise
                logger.exception(
                    f"Unhandled exception during gRPC processing: {error!r}"
                )
                details = (
                    traceback.format_exc() if self.__debug else InternalError.message
                )
                await context.abort(grpc.StatusCode.INTERNAL, details)

        return wrapper

    def _wrap_stream_behavior(
        self,
        behavior: Callable[..., AsyncIterator[object]],
    ) -> Callable[..., AsyncIterator[object]]:
        """Wrap a streaming response handler with error handling."""

        async def wrapper(
            request_or_iterator: object,
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[object]:
            try:
                async for response in behavior(request_or_iterator, context):
                    yield response
            except AbstractGrpcStatusError as error:
                await context.abort(error.status_code, error.message)
            except Exception as error:
                if isinstance(error, grpc.aio.BaseError):
                    raise
                logger.exception(
                    f"Unhandled exception during gRPC processing: {error!r}"
                )
                details = (
                    traceback.format_exc() if self.__debug else InternalError.message
                )
                await context.abort(grpc.StatusCode.INTERNAL, details)

        return wrapper

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept an RPC and wrap the handler with error handling.

        Args:
            continuation: Calls the next interceptor or resolves the handler.
            handler_call_details: Describes the incoming RPC.

        Returns:
            A handler with error-catching wrappers on its behavior methods.
        """
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler  # type: ignore[return-value] — unimplemented method
        return _WrappedHandler(
            handler,
            wrap_unary=self._wrap_unary_behavior,
            wrap_stream=self._wrap_stream_behavior,
        )


class _WrappedHandler(grpc.RpcMethodHandler):
    """Proxy that delegates to the original handler with wrapped behaviors."""

    def __init__(
        self,
        handler: grpc.RpcMethodHandler,
        wrap_unary: Callable[
            ..., Any
        ],  # Any: grpc stubs mix sync/async handler signatures
        wrap_stream: Callable[
            ..., Any
        ],  # Any: grpc stubs mix sync/async handler signatures
    ) -> None:
        self.request_streaming = handler.request_streaming
        self.response_streaming = handler.response_streaming
        self.request_deserializer = handler.request_deserializer
        self.response_serializer = handler.response_serializer
        self.unary_unary = (
            wrap_unary(handler.unary_unary) if handler.unary_unary else None
        )  # type: ignore[arg-type] — grpc stubs define sync handler types but grpc.aio uses async
        self.stream_unary = (
            wrap_unary(handler.stream_unary) if handler.stream_unary else None
        )  # type: ignore[arg-type] — grpc stubs define sync handler types but grpc.aio uses async
        self.unary_stream = (
            wrap_stream(handler.unary_stream) if handler.unary_stream else None
        )  # type: ignore[arg-type] — grpc stubs define sync handler types but grpc.aio uses async
        self.stream_stream = (
            wrap_stream(handler.stream_stream) if handler.stream_stream else None
        )  # type: ignore[arg-type] — grpc stubs define sync handler types but grpc.aio uses async
