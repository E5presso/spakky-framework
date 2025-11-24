"""Context management middleware for request isolation.

Ensures proper isolation of context-scoped dependencies between requests
by clearing the context at the start of each request.
"""

from typing import Awaitable, Callable, TypeAlias

from fastapi import Request
from spakky.pod.interfaces.application_context import IApplicationContext
from starlette.middleware.base import BaseHTTPMiddleware, DispatchFunction
from starlette.responses import Response
from starlette.types import ASGIApp

Next: TypeAlias = Callable[[Request], Awaitable[Response]]


class ManageContextMiddleware(BaseHTTPMiddleware):
    """Middleware that manages application context lifecycle per request.

    Clears the application context at the start of each request to ensure
    context-scoped Pods are properly isolated between requests.
    """

    __application_context: IApplicationContext

    def __init__(
        self,
        app: ASGIApp,
        application_context: IApplicationContext,
        dispatch: DispatchFunction | None = None,
    ) -> None:
        """Initialize the context management middleware.

        Args:
            app: The ASGI application.
            application_context: The application context to manage.
            dispatch: Optional custom dispatch function.
        """
        super().__init__(app, dispatch)
        self.__application_context = application_context

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Process the request with context management.

        Clears the application context before processing the request to ensure
        context-scoped dependencies are fresh for each request.

        Args:
            request: The incoming HTTP request.
            call_next: Function to call the next middleware or route handler.

        Returns:
            The HTTP response from the next middleware or route handler.
        """
        self.__application_context.clear_context()
        return await call_next(request)
