"""Unit tests for Python type → protobuf type mapping."""

from dataclasses import dataclass
from typing import Optional

import pytest
from google.protobuf.descriptor_pb2 import FieldDescriptorProto

from spakky.plugins.grpc.error import UnsupportedTypeError
from spakky.plugins.grpc.schema.type_map import (
    SCALAR_TYPE_MAP,
    is_message_type,
    is_optional,
    is_repeated,
    resolve_proto_type,
    unwrap_optional,
    unwrap_repeated,
)


def test_scalar_type_map_contains_str() -> None:
    """SCALAR_TYPE_MAP should map str to TYPE_STRING."""
    assert SCALAR_TYPE_MAP[str] == FieldDescriptorProto.TYPE_STRING


def test_scalar_type_map_contains_int() -> None:
    """SCALAR_TYPE_MAP should map int to TYPE_INT64."""
    assert SCALAR_TYPE_MAP[int] == FieldDescriptorProto.TYPE_INT64


def test_scalar_type_map_contains_float() -> None:
    """SCALAR_TYPE_MAP should map float to TYPE_DOUBLE."""
    assert SCALAR_TYPE_MAP[float] == FieldDescriptorProto.TYPE_DOUBLE


def test_scalar_type_map_contains_bool() -> None:
    """SCALAR_TYPE_MAP should map bool to TYPE_BOOL."""
    assert SCALAR_TYPE_MAP[bool] == FieldDescriptorProto.TYPE_BOOL


def test_scalar_type_map_contains_bytes() -> None:
    """SCALAR_TYPE_MAP should map bytes to TYPE_BYTES."""
    assert SCALAR_TYPE_MAP[bytes] == FieldDescriptorProto.TYPE_BYTES


def test_is_optional_with_optional_type() -> None:
    """is_optional should return True for Optional[str]."""
    assert is_optional(Optional[str]) is True


def test_is_optional_with_plain_type() -> None:
    """is_optional should return False for plain str."""
    assert is_optional(str) is False


def test_is_optional_with_list_type() -> None:
    """is_optional should return False for list[str]."""
    assert is_optional(list[str]) is False


def test_unwrap_optional_extracts_inner_type() -> None:
    """unwrap_optional should extract str from Optional[str]."""
    assert unwrap_optional(Optional[str]) is str


def test_unwrap_optional_with_dataclass() -> None:
    """unwrap_optional should extract a dataclass from Optional[DC]."""

    @dataclass
    class Inner:
        value: str

    assert unwrap_optional(Optional[Inner]) is Inner


def test_is_repeated_with_list_type() -> None:
    """is_repeated should return True for list[str]."""
    assert is_repeated(list[str]) is True


def test_is_repeated_with_plain_type() -> None:
    """is_repeated should return False for plain str."""
    assert is_repeated(str) is False


def test_unwrap_repeated_extracts_element_type() -> None:
    """unwrap_repeated should extract str from list[str]."""
    assert unwrap_repeated(list[str]) is str


def test_is_message_type_with_dataclass() -> None:
    """is_message_type should return True for a dataclass."""

    @dataclass
    class Msg:
        value: str

    assert is_message_type(Msg) is True


def test_is_message_type_with_scalar() -> None:
    """is_message_type should return False for a scalar type."""
    assert is_message_type(str) is False


def test_resolve_proto_type_for_str() -> None:
    """resolve_proto_type should return TYPE_STRING for str."""
    assert resolve_proto_type(str) == FieldDescriptorProto.TYPE_STRING


def test_resolve_proto_type_for_int() -> None:
    """resolve_proto_type should return TYPE_INT64 for int."""
    assert resolve_proto_type(int) == FieldDescriptorProto.TYPE_INT64


def test_resolve_proto_type_for_float() -> None:
    """resolve_proto_type should return TYPE_DOUBLE for float."""
    assert resolve_proto_type(float) == FieldDescriptorProto.TYPE_DOUBLE


def test_resolve_proto_type_for_bool() -> None:
    """resolve_proto_type should return TYPE_BOOL for bool."""
    assert resolve_proto_type(bool) == FieldDescriptorProto.TYPE_BOOL


def test_resolve_proto_type_for_bytes() -> None:
    """resolve_proto_type should return TYPE_BYTES for bytes."""
    assert resolve_proto_type(bytes) == FieldDescriptorProto.TYPE_BYTES


def test_resolve_proto_type_for_dataclass() -> None:
    """resolve_proto_type should return TYPE_MESSAGE for a dataclass."""

    @dataclass
    class Msg:
        value: str

    assert resolve_proto_type(Msg) == FieldDescriptorProto.TYPE_MESSAGE


def test_resolve_proto_type_unsupported_type_expect_error() -> None:
    """resolve_proto_type should raise UnsupportedTypeError for unsupported types."""
    with pytest.raises(UnsupportedTypeError) as exc_info:
        resolve_proto_type(complex)

    assert exc_info.value.python_type is complex
