"""gRPC plugin error hierarchy.

Provides base error classes, gRPC status-mapped errors, and schema errors.
"""

from abc import ABC
from typing import ClassVar

import grpc
from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyGrpcError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for all Spakky gRPC errors."""

    ...


class AbstractGrpcStatusError(AbstractSpakkyGrpcError, ABC):
    """Base for gRPC errors that map to a specific status code.

    Subclasses must define ``status_code`` to specify which gRPC status
    code the error maps to.
    """

    status_code: ClassVar[grpc.StatusCode]


class InvalidArgument(AbstractGrpcStatusError):
    """gRPC INVALID_ARGUMENT error."""

    message = "Invalid Argument"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.INVALID_ARGUMENT


class NotFound(AbstractGrpcStatusError):
    """gRPC NOT_FOUND error."""

    message = "Not Found"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.NOT_FOUND


class AlreadyExists(AbstractGrpcStatusError):
    """gRPC ALREADY_EXISTS error."""

    message = "Already Exists"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.ALREADY_EXISTS


class PermissionDenied(AbstractGrpcStatusError):
    """gRPC PERMISSION_DENIED error."""

    message = "Permission Denied"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.PERMISSION_DENIED


class Unauthenticated(AbstractGrpcStatusError):
    """gRPC UNAUTHENTICATED error."""

    message = "Unauthenticated"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.UNAUTHENTICATED


class FailedPrecondition(AbstractGrpcStatusError):
    """gRPC FAILED_PRECONDITION error."""

    message = "Failed Precondition"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.FAILED_PRECONDITION


class Unavailable(AbstractGrpcStatusError):
    """gRPC UNAVAILABLE error."""

    message = "Unavailable"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.UNAVAILABLE


class InternalError(AbstractGrpcStatusError):
    """gRPC INTERNAL error."""

    message = "Internal Server Error"
    status_code: ClassVar[grpc.StatusCode] = grpc.StatusCode.INTERNAL


class UnsupportedFieldTypeError(AbstractSpakkyGrpcError):
    """Raised when a Python type cannot be mapped to a protobuf type."""

    message = "Unsupported field type for protobuf mapping"

    def __init__(self, field_type: type[object]) -> None:
        super().__init__()
        self.field_type = field_type


class MissingProtoFieldAnnotationError(AbstractSpakkyGrpcError):
    """Raised when a BaseModel field lacks a ProtoField annotation."""

    message = "Missing ProtoField annotation on BaseModel field"

    def __init__(self, model_type: type, field_name: str) -> None:
        super().__init__()
        self.model_type = model_type
        self.field_name = field_name


class UnsupportedResponseTypeError(AbstractSpakkyGrpcError):
    """Raised when a serializer receives an object it cannot encode.

    The gRPC response serializer accepts either a protobuf ``Message``
    (passed through verbatim) or a pydantic ``BaseModel`` (encoded via
    the ``json_format`` bridge). Any other type signals a controller
    returned an unsupported value.
    """

    message = "Unsupported response type for gRPC serializer"

    def __init__(self, value_type: type[object]) -> None:
        super().__init__()
        self.value_type = value_type


class DescriptorAlreadyRegisteredError(AbstractSpakkyGrpcError):
    """Raised when a FileDescriptorProto is registered more than once."""

    message = "Descriptor already registered in pool"

    def __init__(self, file_name: str) -> None:
        super().__init__()
        self.file_name = file_name
