"""Shared utilities for gRPC server interceptors."""

from typing import Any, Callable

import grpc


def wrap_rpc_behavior(
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
