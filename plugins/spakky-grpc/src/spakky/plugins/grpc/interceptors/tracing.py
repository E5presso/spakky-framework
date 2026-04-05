"""Tracing interceptor for W3C Trace Context propagation over gRPC.

Extracts trace context from incoming gRPC metadata, activates a child
span for the RPC lifetime, and injects trace context into trailing
metadata.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import grpc
import grpc.aio

from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator


class TracingInterceptor(grpc.aio.ServerInterceptor):
    """Interceptor that propagates W3C Trace Context across gRPC boundaries.

    Extracts ``traceparent`` / ``tracestate`` from incoming request
    metadata, activates a child span for the RPC lifetime, and injects
    the current trace context into trailing metadata.
    """

    __propagator: ITracePropagator

    def __init__(self, *, propagator: ITracePropagator) -> None:
        """Initialize the tracing interceptor.

        Args:
            propagator: Trace context propagator for extract/inject.
        """
        self.__propagator = propagator

    @staticmethod
    def _metadata_to_dict(
        metadata: tuple[tuple[str, str | bytes], ...] | None,
    ) -> dict[str, str]:
        """Convert gRPC invocation metadata to a plain string dictionary."""
        if metadata is None:
            return {}
        result: dict[str, str] = {}
        for key, value in metadata:
            result[key] = (
                value
                if isinstance(value, str)
                else value.decode("utf-8", errors="replace")
            )
        return result

    def _wrap_unary_behavior(
        self,
        behavior: Callable[..., Awaitable[object]],
    ) -> Callable[..., Awaitable[object]]:
        """Wrap a unary response handler with trace context lifecycle."""

        async def wrapper(
            request_or_iterator: object,
            context: grpc.aio.ServicerContext,
        ) -> object:
            try:
                result = await behavior(request_or_iterator, context)
                trailing: dict[str, str] = {}
                self.__propagator.inject(trailing)
                if trailing:
                    context.set_trailing_metadata(tuple(trailing.items()))
                return result
            finally:
                TraceContext.clear()

        return wrapper

    def _wrap_stream_behavior(
        self,
        behavior: Callable[..., AsyncIterator[object]],
    ) -> Callable[..., AsyncIterator[object]]:
        """Wrap a streaming response handler with trace context lifecycle."""

        async def wrapper(
            request_or_iterator: object,
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[object]:
            try:
                async for response in behavior(request_or_iterator, context):
                    yield response
                trailing: dict[str, str] = {}
                self.__propagator.inject(trailing)
                if trailing:
                    context.set_trailing_metadata(tuple(trailing.items()))
            finally:
                TraceContext.clear()

        return wrapper

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        """Intercept an RPC and set up W3C Trace Context.

        Extracts trace context from incoming metadata, creates a child span
        (or a new root when no parent exists), and wraps the handler to inject
        trace context into trailing metadata and clear it after completion.

        Args:
            continuation: Calls the next interceptor or resolves the handler.
            handler_call_details: Describes the incoming RPC.

        Returns:
            A handler with trace-context lifecycle wrappers.
        """
        carrier = self._metadata_to_dict(handler_call_details.invocation_metadata)
        parent = self.__propagator.extract(carrier)
        ctx = parent.child() if parent is not None else TraceContext.new_root()
        TraceContext.set(ctx)

        try:
            handler = await continuation(handler_call_details)
        except Exception:
            TraceContext.clear()
            raise

        if handler is None:
            TraceContext.clear()
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
