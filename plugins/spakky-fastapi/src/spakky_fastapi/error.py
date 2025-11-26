"""HTTP error classes for FastAPI integration.

Provides base error classes and common HTTP error responses that integrate
with FastAPI's error handling system. All errors can be converted to JSON
responses with appropriate HTTP status codes.
"""

import traceback
from abc import ABC
from typing import ClassVar

from fastapi import status
from fastapi.responses import JSONResponse, ORJSONResponse
from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyFastAPIError(AbstractSpakkyFrameworkError, ABC):
    """Base error class for FastAPI-related exceptions.

    Provides automatic conversion to FastAPI JSON responses with appropriate
    HTTP status codes. Subclasses should define a status_code class variable.

    Attributes:
        status_code: HTTP status code for this error type.
        message: Human-readable error message.
    """

    status_code: ClassVar[int]
    """HTTP status code returned for this error type."""

    def __init__(self, message: str | None = None, *args: object) -> None:
        """Initialize the error with an optional custom message.

        Args:
            message: Custom error message. If None, uses the class default.
            *args: Additional arguments passed to the base exception.
        """
        if message is not None:
            super().__init__(message)
        else:
            super().__init__(self.message)

    def to_response(self, show_traceback: bool = False) -> JSONResponse:
        """Convert the error to a FastAPI JSON response.

        Args:
            show_traceback: Whether to include the full traceback in the response.

        Returns:
            A JSON response containing the error message, args, and optional traceback.
        """
        return ORJSONResponse(
            content={
                "message": self.message,
                "args": [str(x) for x in self.args],
                "traceback": traceback.format_exc() if show_traceback else None,
            },
            status_code=self.status_code,
        )


class BadRequest(AbstractSpakkyFastAPIError):
    """HTTP 400 Bad Request error."""

    message: str = "Bad Request"
    status_code: ClassVar[int] = status.HTTP_400_BAD_REQUEST


class Unauthorized(AbstractSpakkyFastAPIError):
    """HTTP 401 Unauthorized error."""

    message: str = "Unauthorized"
    status_code: ClassVar[int] = status.HTTP_401_UNAUTHORIZED


class Forbidden(AbstractSpakkyFastAPIError):
    """HTTP 403 Forbidden error."""

    message: str = "Forbidden"
    status_code: ClassVar[int] = status.HTTP_403_FORBIDDEN


class NotFound(AbstractSpakkyFastAPIError):
    """HTTP 404 Not Found error."""

    message: str = "Not Found"
    status_code: ClassVar[int] = status.HTTP_404_NOT_FOUND


class Conflict(AbstractSpakkyFastAPIError):
    """HTTP 409 Conflict error."""

    message: str = "Conflict"
    status_code: ClassVar[int] = status.HTTP_409_CONFLICT


class InternalServerError(AbstractSpakkyFastAPIError):
    """HTTP 500 Internal Server Error."""

    message: str = "Internal Server Error"
    status_code: ClassVar[int] = status.HTTP_500_INTERNAL_SERVER_ERROR
