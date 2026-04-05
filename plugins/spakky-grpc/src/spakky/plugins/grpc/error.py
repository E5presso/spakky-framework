"""gRPC error classes for Spakky framework integration.

Provides base error classes and common gRPC error responses that integrate
with gRPC's status code system. All errors map to appropriate gRPC status
codes for automatic conversion by the ErrorHandlingInterceptor.
"""

from abc import ABC
from typing import ClassVar

from grpc import StatusCode

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyGRPCError(AbstractSpakkyFrameworkError, ABC):
    """Base error class for gRPC-related exceptions.

    Provides automatic mapping to gRPC status codes. Subclasses should
    define a ``status_code`` class variable with the appropriate
    ``grpc.StatusCode``.

    Attributes:
        status_code: gRPC status code for this error type.
        message: Human-readable error message.
    """

    status_code: ClassVar[StatusCode]
    """gRPC status code returned for this error type."""


class InvalidArgument(AbstractSpakkyGRPCError):
    """gRPC INVALID_ARGUMENT error."""

    message = "Invalid Argument"
    status_code: ClassVar[StatusCode] = StatusCode.INVALID_ARGUMENT


class NotFound(AbstractSpakkyGRPCError):
    """gRPC NOT_FOUND error."""

    message = "Not Found"
    status_code: ClassVar[StatusCode] = StatusCode.NOT_FOUND


class AlreadyExists(AbstractSpakkyGRPCError):
    """gRPC ALREADY_EXISTS error."""

    message = "Already Exists"
    status_code: ClassVar[StatusCode] = StatusCode.ALREADY_EXISTS


class PermissionDenied(AbstractSpakkyGRPCError):
    """gRPC PERMISSION_DENIED error."""

    message = "Permission Denied"
    status_code: ClassVar[StatusCode] = StatusCode.PERMISSION_DENIED


class Unauthenticated(AbstractSpakkyGRPCError):
    """gRPC UNAUTHENTICATED error."""

    message = "Unauthenticated"
    status_code: ClassVar[StatusCode] = StatusCode.UNAUTHENTICATED


class InternalError(AbstractSpakkyGRPCError):
    """gRPC INTERNAL error."""

    message = "Internal Error"
    status_code: ClassVar[StatusCode] = StatusCode.INTERNAL
