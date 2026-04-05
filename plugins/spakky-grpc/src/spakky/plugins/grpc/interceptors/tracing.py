"""Tracing interceptor for W3C Trace Context propagation over gRPC.

Extracts trace context from incoming gRPC metadata, activates a child span
for the RPC lifetime, and clears the context after completion.
"""

from typing import Any, Awaitable, Callable

import grpc
import grpc.aio

from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.grpc.interceptors.utils import wrap_rpc_behavior


def _metadata_to_dict(
    metadata: tuple[tuple[str, bytes | str], ...] | None,
) -> dict[str, str]:
    """Convert gRPC metadata to a plain dictionary.

    Args:
        metadata: gRPC invocation metadata, or None.

    Returns:
        A dictionary of header key-value pairs.
    """
    if metadata is None:
        return {}
    return {str(key): str(value) for key, value in metadata}


class TracingInterceptor(grpc.aio.ServerInterceptor):
    """gRPC server interceptor for W3C Trace Context propagation.

    Extracts ``traceparent`` / ``tracestate`` from gRPC metadata, creates
    a child span (or new root), sets it as the ambient ``TraceContext``
    for the RPC lifetime, and clears it after completion.
    """

    __propagator: ITracePropagator

    def __init__(self, *, propagator: ITracePropagator) -> None:
        """Initialize the tracing interceptor.

        Args:
            propagator: Trace context propagator for extract/inject.
        """
        self.__propagator = propagator

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept the RPC to propagate trace context.

        Args:
            continuation: Calls the next interceptor or handler lookup.
            handler_call_details: Metadata about the incoming RPC.

        Returns:
            A wrapped RpcMethodHandler with trace context propagation.
        """
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler  # type: ignore[return-value] - None means unserviced RPC

        carrier = _metadata_to_dict(handler_call_details.invocation_metadata)
        parent = self.__propagator.extract(carrier)
        ctx = parent.child() if parent is not None else TraceContext.new_root()

        def _tracing_wrapper(
            behavior: Callable[..., Any],
        ) -> Callable[..., Any]:
            async def wrapper(
                request_or_iterator: Any,
                context: grpc.aio.ServicerContext,
            ) -> Any:
                TraceContext.set(ctx)
                try:
                    return await behavior(request_or_iterator, context)
                finally:
                    TraceContext.clear()

            return wrapper

        return wrap_rpc_behavior(handler, _tracing_wrapper)
