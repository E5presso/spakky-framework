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


class ProtoFieldNumberConflictError(AbstractSpakkyGrpcError):
    """Raised when an explicit ProtoField number collides with an auto-derived one.

    An explicit ``ProtoField(number=N)`` reserves ``N`` for its field. If an
    auto-numbered field in the same message natively hashes to ``N``, silently
    re-hashing the auto field would change its wire number and break
    compatibility. This conflict is surfaced as a build error instead so the
    author pins the auto field's number too or chooses a different ``N``.
    """

    message = "Explicit ProtoField number collides with an auto-derived field number"

    def __init__(
        self,
        model_type: type,
        explicit_field_name: str,
        derived_field_name: str,
        number: int,
    ) -> None:
        super().__init__()
        self.model_type = model_type
        self.explicit_field_name = explicit_field_name
        self.derived_field_name = derived_field_name
        self.number = number


class InvalidProtoFieldNumberError(AbstractSpakkyGrpcError):
    """Raised when an explicit ProtoField number is not a valid protobuf number.

    An explicit ``ProtoField(number=N)`` must fall in the assignable protobuf
    range: ``1`` .. ``536_870_911`` (``2**29 - 1``) and outside the protobuf
    reserved band ``19_000`` .. ``19_999``. The auto-numbering path already
    honors these constraints deterministically, but an explicit override
    bypassed them and only failed later at descriptor-pool build time with an
    opaque protobuf message. This error surfaces the violation at schema-build
    time with the offending field and number so the author corrects it.
    """

    message = "Explicit ProtoField number is outside the valid protobuf range"

    def __init__(self, model_type: type, field_name: str, number: int) -> None:
        super().__init__()
        self.model_type = model_type
        self.field_name = field_name
        self.number = number


class DuplicateProtoFieldNumberError(AbstractSpakkyGrpcError):
    """Raised when two explicit ProtoField numbers collide in one message.

    Each protobuf field number must be unique within its message. Two fields
    carrying the same explicit ``ProtoField(number=N)`` would later be rejected
    by the descriptor pool with an opaque message. This error surfaces the
    duplicate at schema-build time, naming both colliding fields and the shared
    number so the author repins one of them.
    """

    message = "Duplicate explicit ProtoField number within a single message"

    def __init__(
        self,
        model_type: type,
        first_field_name: str,
        second_field_name: str,
        number: int,
    ) -> None:
        super().__init__()
        self.model_type = model_type
        self.first_field_name = first_field_name
        self.second_field_name = second_field_name
        self.number = number
