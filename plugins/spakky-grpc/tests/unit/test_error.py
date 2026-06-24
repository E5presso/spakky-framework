"""Unit tests for gRPC error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.plugins.grpc.error import (
    AbstractSpakkyGrpcError,
    DescriptorAlreadyRegisteredError,
    ProtoFieldNumberConflictError,
    UnsupportedFieldTypeError,
)


def test_abstract_spakky_grpc_error_is_abstract() -> None:
    """AbstractSpakkyGrpcError가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSpakkyGrpcError, ABC)


def test_abstract_spakky_grpc_error_inherits_from_framework_error() -> None:
    """AbstractSpakkyGrpcError가 AbstractSpakkyFrameworkError를 상속하는지 검증한다."""
    assert issubclass(AbstractSpakkyGrpcError, AbstractSpakkyFrameworkError)


def test_unsupported_field_type_error_is_grpc_error() -> None:
    """UnsupportedFieldTypeError가 AbstractSpakkyGrpcError의 서브클래스인지 검증한다."""
    assert issubclass(UnsupportedFieldTypeError, AbstractSpakkyGrpcError)


def test_unsupported_field_type_error_stores_field_type() -> None:
    """UnsupportedFieldTypeError가 field_type을 저장하는지 검증한다."""
    error = UnsupportedFieldTypeError(int)
    assert error.field_type is int


def test_descriptor_already_registered_error_is_grpc_error() -> None:
    """DescriptorAlreadyRegisteredError가 AbstractSpakkyGrpcError의 서브클래스인지 검증한다."""
    assert issubclass(DescriptorAlreadyRegisteredError, AbstractSpakkyGrpcError)


def test_descriptor_already_registered_error_stores_file_name() -> None:
    """DescriptorAlreadyRegisteredError가 file_name을 저장하는지 검증한다."""
    error = DescriptorAlreadyRegisteredError("test.proto")
    assert error.file_name == "test.proto"


def test_proto_field_number_conflict_error_is_grpc_error() -> None:
    """ProtoFieldNumberConflictError가 AbstractSpakkyGrpcError의 서브클래스인지 검증한다."""
    assert issubclass(ProtoFieldNumberConflictError, AbstractSpakkyGrpcError)


def test_proto_field_number_conflict_error_stores_context() -> None:
    """ProtoFieldNumberConflictError가 충돌 컨텍스트를 저장하는지 검증한다."""

    class Dummy:
        pass

    error = ProtoFieldNumberConflictError(Dummy, "pinned", "name", 95775423)
    assert error.model_type is Dummy
    assert error.explicit_field_name == "pinned"
    assert error.derived_field_name == "name"
    assert error.number == 95775423
