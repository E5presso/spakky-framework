"""Error types for gRPC plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyGrpcError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky gRPC errors."""

    ...


class UnsupportedTypeError(AbstractSpakkyGrpcError):
    """Raised when a Python type cannot be mapped to a protobuf type."""

    message = "Unsupported Python type for protobuf mapping"

    def __init__(self, python_type: type) -> None:
        super().__init__()
        self.python_type = python_type


class MissingProtoFieldError(AbstractSpakkyGrpcError):
    """Raised when a dataclass field lacks a ProtoField annotation."""

    message = "Dataclass field missing ProtoField annotation"

    def __init__(self, dataclass_type: type, field_name: str) -> None:
        super().__init__()
        self.dataclass_type = dataclass_type
        self.field_name = field_name


class DuplicateFieldNumberError(AbstractSpakkyGrpcError):
    """Raised when duplicate field numbers are found in a dataclass."""

    message = "Duplicate protobuf field number in dataclass"

    def __init__(self, dataclass_type: type, field_number: int) -> None:
        super().__init__()
        self.dataclass_type = dataclass_type
        self.field_number = field_number


class DescriptorAlreadyRegisteredError(AbstractSpakkyGrpcError):
    """Raised when attempting to register a descriptor that is already registered."""

    message = "Descriptor already registered in pool"

    def __init__(self, file_name: str) -> None:
        super().__init__()
        self.file_name = file_name
