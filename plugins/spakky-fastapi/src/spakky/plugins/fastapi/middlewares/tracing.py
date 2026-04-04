"""Tracing middleware for W3C Trace Context propagation.

Extracts trace context from incoming HTTP request headers, activates a
child span for the request lifetime, and injects trace context into
response headers.
"""

from typing import Awaitable, Callable, TypeAlias

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, DispatchFunction
from starlette.responses import Response
from starlette.types import ASGIApp

from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

Next: TypeAlias = Callable[[Request], Awaitable[Response]]


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware that propagates W3C Trace Context across HTTP boundaries.

    Extracts ``traceparent`` from request headers, activates a child span
    for the request lifetime, and injects ``traceparent`` into response
    headers.  When no incoming trace context is present, a new root trace
    is started.
    """

    __propagator: ITracePropagator

    def __init__(
        self,
        app: ASGIApp,
        dispatch: DispatchFunction | None = None,
        *,
        propagator: ITracePropagator,
    ) -> None:
        """Initialize the tracing middleware.

        Args:
            app: The ASGI application.
            dispatch: Optional custom dispatch function.
            propagator: Trace context propagator for extract/inject.
        """
        super().__init__(app, dispatch)
        self.__propagator = propagator

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Extract trace context, process request, and inject into response.

        Args:
            request: The incoming HTTP request.
            call_next: Function to call the next middleware or route handler.

        Returns:
            The HTTP response with trace context headers injected.
        """
        carrier: dict[str, str] = dict(request.headers)
        parent = self.__propagator.extract(carrier)
        ctx = parent.child() if parent is not None else TraceContext.new_root()
        TraceContext.set(ctx)
        try:
            response = await call_next(request)
            response_carrier: dict[str, str] = {}
            self.__propagator.inject(response_carrier)
            for key, value in response_carrier.items():
                response.headers[key] = value
            return response
        finally:
            TraceContext.clear()
