"""Unit tests for dataclass → FileDescriptorProto builder."""

from dataclasses import dataclass
from typing import Annotated, Optional

import pytest
from google.protobuf.descriptor_pb2 import FieldDescriptorProto

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import (
    DuplicateFieldNumberError,
    MissingProtoFieldError,
)
from spakky.plugins.grpc.schema.descriptor_builder import (
    build_file_descriptor,
    build_message_descriptor,
    build_service_descriptor,
)


@dataclass
class SimpleMessage:
    """Simple message with scalar fields."""

    name: Annotated[str, ProtoField(number=1)]
    age: Annotated[int, ProtoField(number=2)]
    score: Annotated[float, ProtoField(number=3)]
    active: Annotated[bool, ProtoField(number=4)]
    data: Annotated[bytes, ProtoField(number=5)]


@dataclass
class InnerMessage:
    """Nested message type."""

    value: Annotated[str, ProtoField(number=1)]


@dataclass
class OuterMessage:
    """Message with a nested dataclass reference."""

    title: Annotated[str, ProtoField(number=1)]
    inner: Annotated[InnerMessage, ProtoField(number=2)]


@dataclass
class RepeatedMessage:
    """Message with repeated fields."""

    tags: Annotated[list[str], ProtoField(number=1)]
    items: Annotated[list[InnerMessage], ProtoField(number=2)]


@dataclass
class OptionalMessage:
    """Message with optional fields."""

    nickname: Annotated[Optional[str], ProtoField(number=1)]
    detail: Annotated[Optional[InnerMessage], ProtoField(number=2)]


@dataclass
class RequestMsg:
    """Request message for RPC tests."""

    query: Annotated[str, ProtoField(number=1)]


@dataclass
class ResponseMsg:
    """Response message for RPC tests."""

    result: Annotated[str, ProtoField(number=1)]


def test_build_message_descriptor_scalar_fields() -> None:
    """build_message_descriptor should produce correct scalar field types."""
    msg_desc, refs = build_message_descriptor(SimpleMessage, "test.v1")

    assert msg_desc.name == "SimpleMessage"
    assert len(msg_desc.field) == 5

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["name"].type == FieldDescriptorProto.TYPE_STRING
    assert field_map["name"].number == 1
    assert field_map["age"].type == FieldDescriptorProto.TYPE_INT64
    assert field_map["age"].number == 2
    assert field_map["score"].type == FieldDescriptorProto.TYPE_DOUBLE
    assert field_map["score"].number == 3
    assert field_map["active"].type == FieldDescriptorProto.TYPE_BOOL
    assert field_map["active"].number == 4
    assert field_map["data"].type == FieldDescriptorProto.TYPE_BYTES
    assert field_map["data"].number == 5
    assert refs == []


def test_build_message_descriptor_nested_dataclass() -> None:
    """build_message_descriptor should handle nested dataclass references."""
    msg_desc, refs = build_message_descriptor(OuterMessage, "test.v1")

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["inner"].type == FieldDescriptorProto.TYPE_MESSAGE
    assert field_map["inner"].type_name == ".test.v1.InnerMessage"
    assert InnerMessage in refs


def test_build_message_descriptor_repeated_scalar() -> None:
    """build_message_descriptor should produce LABEL_REPEATED for list fields."""
    msg_desc, _ = build_message_descriptor(RepeatedMessage, "test.v1")

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["tags"].label == FieldDescriptorProto.LABEL_REPEATED
    assert field_map["tags"].type == FieldDescriptorProto.TYPE_STRING


def test_build_message_descriptor_repeated_message() -> None:
    """build_message_descriptor should handle repeated message fields."""
    msg_desc, refs = build_message_descriptor(RepeatedMessage, "test.v1")

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["items"].label == FieldDescriptorProto.LABEL_REPEATED
    assert field_map["items"].type == FieldDescriptorProto.TYPE_MESSAGE
    assert field_map["items"].type_name == ".test.v1.InnerMessage"
    assert InnerMessage in refs


def test_build_message_descriptor_optional_scalar() -> None:
    """build_message_descriptor should set proto3_optional for Optional scalar."""
    msg_desc, _ = build_message_descriptor(OptionalMessage, "test.v1")

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["nickname"].proto3_optional is True
    assert field_map["nickname"].type == FieldDescriptorProto.TYPE_STRING


def test_build_message_descriptor_optional_message() -> None:
    """build_message_descriptor should set proto3_optional for Optional message."""
    msg_desc, refs = build_message_descriptor(OptionalMessage, "test.v1")

    field_map = {f.name: f for f in msg_desc.field}
    assert field_map["detail"].proto3_optional is True
    assert field_map["detail"].type == FieldDescriptorProto.TYPE_MESSAGE
    assert InnerMessage in refs


def test_build_message_descriptor_optional_oneof_decl() -> None:
    """build_message_descriptor should create oneof_decl entries for optional fields."""
    msg_desc, _ = build_message_descriptor(OptionalMessage, "test.v1")

    assert len(msg_desc.oneof_decl) == 2
    assert msg_desc.oneof_decl[0].name == "_nickname"
    assert msg_desc.oneof_decl[1].name == "_detail"


def test_build_message_descriptor_duplicate_field_number_expect_error() -> None:
    """build_message_descriptor should raise DuplicateFieldNumberError for duplicate numbers."""

    @dataclass
    class DuplicateMsg:
        a: Annotated[str, ProtoField(number=1)]
        b: Annotated[int, ProtoField(number=1)]

    with pytest.raises(DuplicateFieldNumberError) as exc_info:
        build_message_descriptor(DuplicateMsg, "test.v1")

    assert exc_info.value.dataclass_type is DuplicateMsg
    assert exc_info.value.field_number == 1


def test_build_message_descriptor_missing_proto_field_expect_error() -> None:
    """build_message_descriptor should raise MissingProtoFieldError for unannotated fields."""

    @dataclass
    class NoAnnotation:
        name: str

    with pytest.raises(MissingProtoFieldError) as exc_info:
        build_message_descriptor(NoAnnotation, "test.v1")

    assert exc_info.value.dataclass_type is NoAnnotation
    assert exc_info.value.field_name == "name"


def test_build_service_descriptor_unary_method() -> None:
    """build_service_descriptor should build correct unary method descriptors."""

    class TestService:
        @rpc()
        async def get_item(self, request: RequestMsg) -> ResponseMsg: ...

    svc_desc, types = build_service_descriptor(TestService, "TestService", "test.v1")

    assert svc_desc.name == "TestService"
    assert len(svc_desc.method) == 1
    method = svc_desc.method[0]
    assert method.name == "get_item"
    assert method.input_type == ".test.v1.RequestMsg"
    assert method.output_type == ".test.v1.ResponseMsg"
    assert method.client_streaming is False
    assert method.server_streaming is False
    assert RequestMsg in types
    assert ResponseMsg in types


def test_build_service_descriptor_server_streaming_method() -> None:
    """build_service_descriptor should set server_streaming for SERVER_STREAMING."""

    class TestService:
        @rpc(method_type=RpcMethodType.SERVER_STREAMING)
        async def list_items(self, request: RequestMsg) -> ResponseMsg: ...

    svc_desc, _ = build_service_descriptor(TestService, "TestService", "test.v1")
    method = svc_desc.method[0]
    assert method.server_streaming is True
    assert method.client_streaming is False


def test_build_service_descriptor_client_streaming_method() -> None:
    """build_service_descriptor should set client_streaming for CLIENT_STREAMING."""

    class TestService:
        @rpc(method_type=RpcMethodType.CLIENT_STREAMING)
        async def record(self, request: RequestMsg) -> ResponseMsg: ...

    svc_desc, _ = build_service_descriptor(TestService, "TestService", "test.v1")
    method = svc_desc.method[0]
    assert method.client_streaming is True
    assert method.server_streaming is False


def test_build_service_descriptor_bidi_streaming_method() -> None:
    """build_service_descriptor should set both streaming flags for BIDI_STREAMING."""

    class TestService:
        @rpc(method_type=RpcMethodType.BIDI_STREAMING)
        async def chat(self, request: RequestMsg) -> ResponseMsg: ...

    svc_desc, _ = build_service_descriptor(TestService, "TestService", "test.v1")
    method = svc_desc.method[0]
    assert method.client_streaming is True
    assert method.server_streaming is True


def test_build_file_descriptor_complete() -> None:
    """build_file_descriptor should produce a complete FileDescriptorProto."""

    class GreeterService:
        @rpc()
        async def greet(self, request: RequestMsg) -> ResponseMsg: ...

    fd = build_file_descriptor("test.v1", "GreeterService", GreeterService)

    assert fd.name == "test/v1/GreeterService.proto"
    assert fd.package == "test.v1"
    assert fd.syntax == "proto3"
    assert len(fd.service) == 1
    assert fd.service[0].name == "GreeterService"
    msg_names = {m.name for m in fd.message_type}
    assert "RequestMsg" in msg_names
    assert "ResponseMsg" in msg_names


def test_build_file_descriptor_deduplicates_messages() -> None:
    """build_file_descriptor should not duplicate message types used by multiple methods."""

    class DualService:
        @rpc()
        async def method_a(self, request: RequestMsg) -> ResponseMsg: ...

        @rpc()
        async def method_b(self, request: RequestMsg) -> ResponseMsg: ...

    fd = build_file_descriptor("test.v1", "DualService", DualService)
    msg_names = [m.name for m in fd.message_type]
    assert msg_names.count("RequestMsg") == 1
    assert msg_names.count("ResponseMsg") == 1


def test_build_file_descriptor_includes_transitive_dependencies() -> None:
    """build_file_descriptor should include transitively referenced message types."""

    @dataclass
    class NestedReq:
        inner: Annotated[InnerMessage, ProtoField(number=1)]

    class NestedService:
        @rpc()
        async def get(self, request: NestedReq) -> ResponseMsg: ...

    fd = build_file_descriptor("test.v1", "NestedService", NestedService)
    msg_names = {m.name for m in fd.message_type}
    assert "NestedReq" in msg_names
    assert "InnerMessage" in msg_names
    assert "ResponseMsg" in msg_names
