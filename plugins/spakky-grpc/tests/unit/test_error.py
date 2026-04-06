"""Unit tests for gRPC error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.plugins.grpc.error import (
    AbstractSpakkyGrpcError,
    DescriptorAlreadyRegisteredError,
    MissingProtoFieldAnnotationError,
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


def test_missing_proto_field_annotation_error_is_grpc_error() -> None:
    """MissingProtoFieldAnnotationError가 AbstractSpakkyGrpcError의 서브클래스인지 검증한다."""
    assert issubclass(MissingProtoFieldAnnotationError, AbstractSpakkyGrpcError)


def test_missing_proto_field_annotation_error_stores_context() -> None:
    """MissingProtoFieldAnnotationError가 dataclass_type과 field_name을 저장하는지 검증한다."""

    class Dummy:
        pass

    error = MissingProtoFieldAnnotationError(Dummy, "name")
    assert error.dataclass_type is Dummy
    assert error.field_name == "name"


def test_descriptor_already_registered_error_is_grpc_error() -> None:
    """DescriptorAlreadyRegisteredError가 AbstractSpakkyGrpcError의 서브클래스인지 검증한다."""
    assert issubclass(DescriptorAlreadyRegisteredError, AbstractSpakkyGrpcError)


def test_descriptor_already_registered_error_stores_file_name() -> None:
    """DescriptorAlreadyRegisteredError가 file_name을 저장하는지 검증한다."""
    error = DescriptorAlreadyRegisteredError("test.proto")
    assert error.file_name == "test.proto"
