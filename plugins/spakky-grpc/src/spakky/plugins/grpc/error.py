"""gRPC error classes for Spakky framework.

Provides base error classes and common gRPC error responses that map
domain exceptions to appropriate gRPC status codes.
"""

from abc import ABC
from typing import ClassVar

import grpc

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyGRPCError(AbstractSpakkyFrameworkError, ABC):
    """Base error class for gRPC-related exceptions.

    Subclasses must define ``status_code`` to specify which gRPC status
    code the error maps to.

    Attributes:
        status_code: gRPC status code for this error type.
        message: Human-readable error message.
    """

    status_code: ClassVar[grpc.StatusCode]
    """gRPC status code returned for this error type."""


class InvalidArgument(AbstractSpakkyGRPCError):
    """gRPC INVALID_ARGUMENT error."""

    message = "Invalid Argument"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.INVALID_ARGUMENT


class NotFound(AbstractSpakkyGRPCError):
    """gRPC NOT_FOUND error."""

    message = "Not Found"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.NOT_FOUND


class AlreadyExists(AbstractSpakkyGRPCError):
    """gRPC ALREADY_EXISTS error."""

    message = "Already Exists"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.ALREADY_EXISTS


class PermissionDenied(AbstractSpakkyGRPCError):
    """gRPC PERMISSION_DENIED error."""

    message = "Permission Denied"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.PERMISSION_DENIED


class Unauthenticated(AbstractSpakkyGRPCError):
    """gRPC UNAUTHENTICATED error."""

    message = "Unauthenticated"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.UNAUTHENTICATED


class FailedPrecondition(AbstractSpakkyGRPCError):
    """gRPC FAILED_PRECONDITION error."""

    message = "Failed Precondition"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.FAILED_PRECONDITION


class Unavailable(AbstractSpakkyGRPCError):
    """gRPC UNAVAILABLE error."""

    message = "Unavailable"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.UNAVAILABLE


class InternalError(AbstractSpakkyGRPCError):
    """gRPC INTERNAL error."""

    message = "Internal Server Error"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.INTERNAL
