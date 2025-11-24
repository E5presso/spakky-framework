"""Error handling middleware for FastAPI applications.

Provides global exception handling that converts Spakky FastAPI errors
to appropriate JSON responses and handles unexpected exceptions gracefully.
"""

from logging import Logger
from typing import Awaitable, Callable, TypeAlias

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, DispatchFunction
from starlette.responses import Response
from starlette.types import ASGIApp

from spakky_fastapi.error import AbstractSpakkyFastAPIError, InternalServerError

Next: TypeAlias = Callable[[Request], Awaitable[Response]]


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware that catches and converts exceptions to JSON responses.

    Handles both Spakky FastAPI errors and unexpected exceptions, converting
    them to appropriate JSON responses with correct HTTP status codes.
    """

    __debug: bool
    __logger: Logger

    def __init__(
        self,
        app: ASGIApp,
        logger: Logger,
        dispatch: DispatchFunction | None = None,
        debug: bool = False,
    ) -> None:
        """Initialize the error handling middleware.

        Args:
            app: The ASGI application.
            dispatch: Optional custom dispatch function.
            debug: Whether to include tracebacks in error responses.
        """
        super().__init__(app, dispatch)
        self.__debug = debug
        self.__logger = logger

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Process the request with error handling.

        Catches exceptions during request processing and converts them to
        appropriate JSON responses. Spakky FastAPI errors are converted using
        their to_response() method, while unexpected exceptions return 500.

        Args:
            request: The incoming HTTP request.
            call_next: Function to call the next middleware or route handler.

        Returns:
            The HTTP response, either from successful processing or error handling.
        """
        try:
            return await call_next(request)
        except AbstractSpakkyFastAPIError as e:
            return e.to_response()
        except Exception as e:
            self.__logger.exception(
                f"Unhandled exception during request processing: {e!r}"
            )
            return InternalServerError().to_response(self.__debug)
