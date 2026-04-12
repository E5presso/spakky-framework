"""Unit tests for type_map module."""

from typing import Annotated, Optional

import pytest
from google.protobuf.descriptor_pb2 import FieldDescriptorProto
from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.error import (
    MissingProtoFieldAnnotationError,
    UnsupportedFieldTypeError,
)
from spakky.plugins.grpc.schema.type_map import (
    PYTHON_TO_PROTO_TYPE,
    ResolvedFieldType,
    extract_proto_field,
    resolve_type,
)


def test_str_maps_to_type_string() -> None:
    """str이 TYPE_STRING으로 매핑되는지 검증한다."""
    result = resolve_type(str)
    assert result.proto_type == FieldDescriptorProto.TYPE_STRING
    assert not result.is_repeated
    assert not result.is_optional
    assert not result.is_message


def test_int_maps_to_type_int64() -> None:
    """int이 TYPE_INT64로 매핑되는지 검증한다."""
    result = resolve_type(int)
    assert result.proto_type == FieldDescriptorProto.TYPE_INT64


def test_float_maps_to_type_double() -> None:
    """float이 TYPE_DOUBLE로 매핑되는지 검증한다."""
    result = resolve_type(float)
    assert result.proto_type == FieldDescriptorProto.TYPE_DOUBLE


def test_bool_maps_to_type_bool() -> None:
    """bool이 TYPE_BOOL로 매핑되는지 검증한다."""
    result = resolve_type(bool)
    assert result.proto_type == FieldDescriptorProto.TYPE_BOOL


def test_bytes_maps_to_type_bytes() -> None:
    """bytes가 TYPE_BYTES로 매핑되는지 검증한다."""
    result = resolve_type(bytes)
    assert result.proto_type == FieldDescriptorProto.TYPE_BYTES


def test_nested_basemodel_maps_to_type_message() -> None:
    """중첩 BaseModel이 TYPE_MESSAGE로 매핑되는지 검증한다."""

    class Inner(BaseModel):
        value: Annotated[str, ProtoField(number=1)]

    result = resolve_type(Inner)
    assert result.proto_type == FieldDescriptorProto.TYPE_MESSAGE
    assert result.is_message
    assert result.message_type is Inner


def test_list_str_maps_to_repeated_string() -> None:
    """list[str]이 repeated TYPE_STRING으로 매핑되는지 검증한다."""
    result = resolve_type(list[str])
    assert result.proto_type == FieldDescriptorProto.TYPE_STRING
    assert result.is_repeated
    assert not result.is_message


def test_list_basemodel_maps_to_repeated_message() -> None:
    """list[BaseModel]이 repeated TYPE_MESSAGE로 매핑되는지 검증한다."""

    class Item(BaseModel):
        name: Annotated[str, ProtoField(number=1)]

    result = resolve_type(list[Item])
    assert result.proto_type == FieldDescriptorProto.TYPE_MESSAGE
    assert result.is_repeated
    assert result.is_message
    assert result.message_type is Item


def test_optional_str_maps_to_optional_string() -> None:
    """Optional[str]이 optional TYPE_STRING으로 매핑되는지 검증한다."""
    result = resolve_type(Optional[str])
    assert result.proto_type == FieldDescriptorProto.TYPE_STRING
    assert result.is_optional
    assert not result.is_repeated


def test_union_none_maps_to_optional() -> None:
    """str | None이 optional TYPE_STRING으로 매핑되는지 검증한다."""
    result = resolve_type(str | None)
    assert result.proto_type == FieldDescriptorProto.TYPE_STRING
    assert result.is_optional


def test_unsupported_type_raises_error() -> None:
    """지원하지 않는 타입에 대해 UnsupportedFieldTypeError를 발생시키는지 검증한다."""
    with pytest.raises(UnsupportedFieldTypeError):
        resolve_type(complex)


def test_extract_proto_field_from_annotated() -> None:
    """Annotated 타입에서 ProtoField를 추출하는지 검증한다."""

    class Msg(BaseModel):
        name: Annotated[str, ProtoField(number=3)]

    result = extract_proto_field(Msg, "name")
    assert result.number == 3


def test_extract_proto_field_missing_raises_error() -> None:
    """존재하지 않는 필드에서 MissingProtoFieldAnnotationError를 발생시키는지 검증한다."""

    class Msg(BaseModel):
        name: str

    with pytest.raises(MissingProtoFieldAnnotationError) as exc_info:
        extract_proto_field(Msg, "name")
    assert exc_info.value.field_name == "name"


def test_python_to_proto_type_has_all_basic_types() -> None:
    """PYTHON_TO_PROTO_TYPE이 기본 5가지 타입을 포함하는지 검증한다."""
    assert str in PYTHON_TO_PROTO_TYPE
    assert int in PYTHON_TO_PROTO_TYPE
    assert float in PYTHON_TO_PROTO_TYPE
    assert bool in PYTHON_TO_PROTO_TYPE
    assert bytes in PYTHON_TO_PROTO_TYPE


def test_resolved_field_type_defaults() -> None:
    """ResolvedFieldType의 기본값을 검증한다."""
    resolved = ResolvedFieldType(proto_type=FieldDescriptorProto.TYPE_STRING)
    assert not resolved.is_repeated
    assert not resolved.is_optional
    assert not resolved.is_message
    assert resolved.message_type is None


def test_bare_list_raises_error() -> None:
    """타입 인자가 없는 list에 대해 UnsupportedFieldTypeError를 발생시키는지 검증한다."""
    with pytest.raises(UnsupportedFieldTypeError):
        resolve_type(list)


def test_multi_type_union_raises_error() -> None:
    """Union[str, int] 같은 다중 타입 유니온에서 UnsupportedFieldTypeError를 발생시키는지 검증한다."""
    from typing import Union

    with pytest.raises(UnsupportedFieldTypeError):
        resolve_type(Union[str, int])


def test_extract_proto_field_multi_field_basemodel() -> None:
    """멀티 필드 BaseModel에서 두 번째 필드의 ProtoField를 추출하는지 검증한다."""

    class Multi(BaseModel):
        first: Annotated[str, ProtoField(number=1)]
        second: Annotated[int, ProtoField(number=2)]

    result = extract_proto_field(Multi, "second")
    assert result.number == 2


def test_optional_basemodel_maps_to_optional_message() -> None:
    """Optional[BaseModel]이 optional TYPE_MESSAGE로 매핑되는지 검증한다."""

    class Inner(BaseModel):
        value: Annotated[str, ProtoField(number=1)]

    result = resolve_type(Optional[Inner])
    assert result.proto_type == FieldDescriptorProto.TYPE_MESSAGE
    assert result.is_optional
    assert result.is_message
    assert result.message_type is Inner


def test_extract_proto_field_nonexistent_field_raises_error() -> None:
    """존재하지 않는 필드명을 요청하면 MissingProtoFieldAnnotationError를 발생시키는지 검증한다."""

    class Msg(BaseModel):
        name: Annotated[str, ProtoField(number=1)]

    with pytest.raises(MissingProtoFieldAnnotationError) as exc_info:
        extract_proto_field(Msg, "nonexistent")
    assert exc_info.value.field_name == "nonexistent"


def test_extract_proto_field_annotated_without_proto_field_raises_error() -> None:
    """Annotated이지만 ProtoField가 없는 필드에서 MissingProtoFieldAnnotationError를 발생시키는지 검증한다."""

    class Msg(BaseModel):
        name: Annotated[str, "not a proto field"]

    with pytest.raises(MissingProtoFieldAnnotationError) as exc_info:
        extract_proto_field(Msg, "name")
    assert exc_info.value.field_name == "name"
