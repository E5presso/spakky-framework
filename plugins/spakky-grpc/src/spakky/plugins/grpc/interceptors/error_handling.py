"""Error handling interceptor for gRPC servers.

Catches domain exceptions and converts them to appropriate gRPC status
codes. Unhandled exceptions are mapped to INTERNAL status.
"""

from logging import getLogger
from typing import Any, Awaitable, Callable

import grpc
import grpc.aio

from spakky.plugins.grpc.error import AbstractSpakkyGRPCError

logger = getLogger(__name__)


def _wrap_rpc_behavior(
    handler: grpc.RpcMethodHandler,
    fn: Callable[..., Any],
) -> grpc.RpcMethodHandler:
    """Wrap the active handler behavior with a new function.

    Replaces whichever of ``unary_unary``, ``unary_stream``,
    ``stream_unary``, or ``stream_stream`` is set on *handler*
    with *fn(original_behavior)*.

    Args:
        handler: The original RPC method handler.
        fn: A wrapper function that takes the original behavior and
            returns a new behavior.

    Returns:
        A new RpcMethodHandler with the wrapped behavior.
    """
    if handler.unary_unary is not None:
        return grpc.unary_unary_rpc_method_handler(
            fn(handler.unary_unary),
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
    if handler.unary_stream is not None:
        return grpc.unary_stream_rpc_method_handler(
            fn(handler.unary_stream),
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
    if handler.stream_unary is not None:
        return grpc.stream_unary_rpc_method_handler(
            fn(handler.stream_unary),
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
    if handler.stream_stream is not None:
        return grpc.stream_stream_rpc_method_handler(
            fn(handler.stream_stream),
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
    return handler


class ErrorHandlingInterceptor(grpc.aio.ServerInterceptor):
    """gRPC server interceptor that catches and converts exceptions.

    Handles ``AbstractSpakkyGRPCError`` subclasses by aborting with the
    mapped gRPC status code and message. Unhandled exceptions are logged
    and converted to ``INTERNAL`` status.
    """

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept the RPC to add error handling around the handler.

        Args:
            continuation: Calls the next interceptor or handler lookup.
            handler_call_details: Metadata about the incoming RPC.

        Returns:
            A wrapped RpcMethodHandler with error handling.
        """
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler  # type: ignore[return-value] - None means unserviced RPC

        def _error_wrapper(
            behavior: Callable[..., Any],
        ) -> Callable[..., Any]:
            async def wrapper(
                request_or_iterator: Any,
                context: grpc.aio.ServicerContext,
            ) -> Any:
                try:
                    return await behavior(request_or_iterator, context)
                except AbstractSpakkyGRPCError as e:
                    await context.abort(e.status_code, e.message)
                except Exception as e:
                    logger.exception(
                        f"Unhandled exception during gRPC request processing: {e!r}"
                    )
                    await context.abort(
                        grpc.StatusCode.INTERNAL, "Internal Server Error"
                    )

            return wrapper

        return _wrap_rpc_behavior(handler, _error_wrapper)
