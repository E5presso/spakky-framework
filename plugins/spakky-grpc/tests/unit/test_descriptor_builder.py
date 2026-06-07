"""Unit tests for descriptor_builder module."""

from typing import Annotated

from google.protobuf.descriptor_pb2 import FieldDescriptorProto
from pydantic import BaseModel

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.schema.descriptor_builder import (
    build_file_descriptor,
    build_message_descriptor,
    build_service_descriptor,
)
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


class HelloRequest(BaseModel):
    """Test request message."""

    name: Annotated[str, ProtoField(number=1)]
    count: Annotated[int, ProtoField(number=2)]


class HelloResponse(BaseModel):
    """Test response message."""

    greeting: Annotated[str, ProtoField(number=1)]


class Address(BaseModel):
    """Nested message for testing."""

    street: Annotated[str, ProtoField(number=1)]
    city: Annotated[str, ProtoField(number=2)]


class Person(BaseModel):
    """Message with nested BaseModel."""

    name: Annotated[str, ProtoField(number=1)]
    address: Annotated[Address, ProtoField(number=2)]


class TeamRequest(BaseModel):
    """Message with repeated field."""

    members: Annotated[list[str], ProtoField(number=1)]


def test_build_message_descriptor_basic_types() -> None:
    """기본 타입 필드가 올바르게 변환되는지 검증한다."""
    descriptor, _collected = build_message_descriptor(HelloRequest)
    assert descriptor.name == "HelloRequest"
    assert len(descriptor.field) == 2

    name_field = descriptor.field[0]
    assert name_field.name == "name"
    assert name_field.number == 1
    assert name_field.type == FieldDescriptorProto.TYPE_STRING

    count_field = descriptor.field[1]
    assert count_field.name == "count"
    assert count_field.number == 2
    assert count_field.type == FieldDescriptorProto.TYPE_INT64


def test_build_message_descriptor_nested_basemodel() -> None:
    """중첩 BaseModel이 재귀적으로 처리되는지 검증한다."""
    descriptor, collected = build_message_descriptor(Person)
    assert descriptor.name == "Person"

    address_field = descriptor.field[1]
    assert address_field.name == "address"
    assert address_field.type == FieldDescriptorProto.TYPE_MESSAGE
    assert address_field.type_name == "Address"
    assert "Address" in collected


def test_build_message_descriptor_repeated_field() -> None:
    """list[T] 필드가 repeated로 변환되는지 검증한다."""
    descriptor, _ = build_message_descriptor(TeamRequest)
    members_field = descriptor.field[0]
    assert members_field.label == FieldDescriptorProto.LABEL_REPEATED
    assert members_field.type == FieldDescriptorProto.TYPE_STRING


def test_build_message_descriptor_deduplicates() -> None:
    """같은 타입이 collected에 중복 등록되지 않는지 검증한다."""
    collected: dict = {}
    build_message_descriptor(HelloRequest, collected)
    build_message_descriptor(HelloRequest, collected)
    assert len(collected) == 1


@GrpcController(package="test.v1")
class SampleGreeterService:
    """Test gRPC service controller."""

    @rpc()
    async def say_hello(self, request: HelloRequest) -> HelloResponse:
        """Unary RPC method."""
        ...


def test_build_service_descriptor_unary() -> None:
    """unary @rpc 메서드에서 서비스 descriptor가 생성되는지 검증한다."""
    collected: dict = {}
    service = build_service_descriptor(
        SampleGreeterService, "test.v1", "SampleGreeterService", collected
    )
    assert service.name == "SampleGreeterService"
    assert len(service.method) == 1

    method = service.method[0]
    assert method.name == "say_hello"
    assert method.input_type == ".test.v1.HelloRequest"
    assert method.output_type == ".test.v1.HelloResponse"

    assert "HelloRequest" in collected
    assert "HelloResponse" in collected


def test_build_service_descriptor_sets_streaming_flags() -> None:
    """Descriptor methods expose the streaming mode selected by @rpc."""

    @GrpcController(package="test.v1")
    class StreamingService:
        """Service with all four RPC streaming modes."""

        @rpc(
            method_type=RpcMethodType.UNARY,
            request_type=HelloRequest,
            response_type=HelloResponse,
        )
        async def unary(self, request: HelloRequest) -> HelloResponse:
            """Unary method."""
            ...

        @rpc(
            method_type=RpcMethodType.SERVER_STREAMING,
            request_type=HelloRequest,
            response_type=HelloResponse,
        )
        async def server_streaming(self, request: HelloRequest) -> HelloResponse:
            """Server-streaming method."""
            ...

        @rpc(
            method_type=RpcMethodType.CLIENT_STREAMING,
            request_type=HelloRequest,
            response_type=HelloResponse,
        )
        async def client_streaming(self, request: HelloRequest) -> HelloResponse:
            """Client-streaming method."""
            ...

        @rpc(
            method_type=RpcMethodType.BIDI_STREAMING,
            request_type=HelloRequest,
            response_type=HelloResponse,
        )
        async def bidi_streaming(self, request: HelloRequest) -> HelloResponse:
            """Bidirectional-streaming method."""
            ...

    service = build_service_descriptor(
        StreamingService, "test.v1", "StreamingService", {}
    )
    methods = {method.name: method for method in service.method}

    assert not methods["unary"].client_streaming
    assert not methods["unary"].server_streaming
    assert not methods["server_streaming"].client_streaming
    assert methods["server_streaming"].server_streaming
    assert methods["client_streaming"].client_streaming
    assert not methods["client_streaming"].server_streaming
    assert methods["bidi_streaming"].client_streaming
    assert methods["bidi_streaming"].server_streaming


def test_build_file_descriptor_complete() -> None:
    """build_file_descriptor가 완전한 FileDescriptorProto를 생성하는지 검증한다."""
    file_desc = build_file_descriptor(SampleGreeterService)
    assert file_desc.name == "test/v1/SampleGreeterService.proto"
    assert file_desc.package == "test.v1"
    assert file_desc.syntax == "proto3"
    assert len(file_desc.service) == 1
    assert len(file_desc.message_type) >= 2

    message_names = {m.name for m in file_desc.message_type}
    assert "HelloRequest" in message_names
    assert "HelloResponse" in message_names


def test_build_file_descriptor_uses_explicit_service_name() -> None:
    """GrpcController에 명시적 service_name이 사용되는지 검증한다."""

    @GrpcController(package="api.v1", service_name="CustomService")
    class MyController:
        """Controller with explicit service name."""

        @rpc()
        async def get_data(self, request: HelloRequest) -> HelloResponse:
            """Unary method."""
            ...

    file_desc = build_file_descriptor(MyController)
    assert file_desc.service[0].name == "CustomService"
    assert file_desc.name == "api/v1/CustomService.proto"


def test_build_message_descriptor_optional_field() -> None:
    """Optional 필드가 proto3_optional로 변환되는지 검증한다."""

    class OptionalMsg(BaseModel):
        """Message with optional field."""

        nickname: Annotated[str | None, ProtoField(number=1)] = None

    descriptor, _ = build_message_descriptor(OptionalMsg)
    field = descriptor.field[0]
    assert field.label == FieldDescriptorProto.LABEL_OPTIONAL
    assert field.proto3_optional is True


def test_build_service_descriptor_no_request_type() -> None:
    """request_type이 None인 rpc 메서드에서 input_type이 빈 문자열인지 검증한다."""

    @GrpcController(package="test.v1")
    class NoRequestService:
        """Service with no-param rpc."""

        @rpc()
        async def no_request(self) -> HelloResponse:
            """RPC with no request type."""
            ...

    collected: dict = {}
    service = build_service_descriptor(
        NoRequestService, "test.v1", "NoRequestService", collected
    )
    method = service.method[0]
    assert method.input_type == ""
    assert method.output_type == ".test.v1.HelloResponse"


def test_build_service_descriptor_no_response_type() -> None:
    """response_type이 None인 rpc 메서드에서 output_type이 빈 문자열인지 검증한다."""

    @GrpcController(package="test.v1")
    class NoResponseService:
        """Service with void-return rpc."""

        @rpc()
        async def fire_and_forget(self, request: HelloRequest):  # type: ignore[no-untyped-def] - intentionally no return type
            """RPC with no response type."""
            ...

    collected: dict = {}
    service = build_service_descriptor(
        NoResponseService, "test.v1", "NoResponseService", collected
    )
    method = service.method[0]
    assert method.input_type == ".test.v1.HelloRequest"
    assert method.output_type == ""


def test_build_service_descriptor_skips_non_rpc_methods() -> None:
    """@rpc가 없는 메서드는 서비스 descriptor에 포함되지 않는지 검증한다."""

    @GrpcController(package="test.v1")
    class MixedService:
        """Service with both rpc and non-rpc methods."""

        @rpc()
        async def greet(self, request: HelloRequest) -> HelloResponse:
            """RPC method."""
            ...

        async def helper(self) -> None:
            """Non-RPC helper method."""
            ...

    collected: dict = {}
    service = build_service_descriptor(
        MixedService, "test.v1", "MixedService", collected
    )
    assert len(service.method) == 1
    assert service.method[0].name == "greet"
