"""Unit tests for gRPC error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.plugins.grpc.error import (
    AbstractSpakkyGrpcError,
    DescriptorAlreadyRegisteredError,
    DuplicateFieldNumberError,
    MissingProtoFieldError,
    UnsupportedTypeError,
)


def test_abstract_spakky_grpc_error_is_abstract() -> None:
    """AbstractSpakkyGrpcError should be an ABC subclass."""
    assert issubclass(AbstractSpakkyGrpcError, ABC)


def test_abstract_spakky_grpc_error_inherits_from_framework_error() -> None:
    """AbstractSpakkyGrpcError should inherit from AbstractSpakkyFrameworkError."""
    assert issubclass(AbstractSpakkyGrpcError, AbstractSpakkyFrameworkError)


def test_unsupported_type_error_stores_python_type() -> None:
    """UnsupportedTypeError should store the unsupported python_type."""
    error = UnsupportedTypeError(complex)
    assert error.python_type is complex


def test_missing_proto_field_error_stores_context() -> None:
    """MissingProtoFieldError should store dataclass_type and field_name."""

    class Dummy:
        pass

    error = MissingProtoFieldError(Dummy, "field_a")
    assert error.dataclass_type is Dummy
    assert error.field_name == "field_a"


def test_duplicate_field_number_error_stores_context() -> None:
    """DuplicateFieldNumberError should store dataclass_type and field_number."""

    class Dummy:
        pass

    error = DuplicateFieldNumberError(Dummy, 42)
    assert error.dataclass_type is Dummy
    assert error.field_number == 42


def test_descriptor_already_registered_error_stores_file_name() -> None:
    """DescriptorAlreadyRegisteredError should store the file_name."""
    error = DescriptorAlreadyRegisteredError("test.proto")
    assert error.file_name == "test.proto"
