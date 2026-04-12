"""Unit tests for GrpcServiceHandler and its json_format bridge helpers."""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio
import pytest
from google.protobuf import json_format
from pydantic import BaseModel
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import UnsupportedResponseTypeError
from spakky.plugins.grpc.handler import (
    GrpcServiceHandler,
    _basemodel_to_protobuf,
    _protobuf_to_basemodel,
)
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


class PingRequest(BaseModel):
    """Test request."""

    value: Annotated[str, ProtoField(number=1)]


class PingReply(BaseModel):
    """Test response."""

    value: Annotated[str, ProtoField(number=1)]


@GrpcController(package="handler.v1")
class PingController:
    """Controller with a unary method for handler tests."""

    @rpc()
    async def ping(self, request: PingRequest) -> PingReply:
        """Echo the value back."""
        return PingReply(value=request.value)


@GrpcController(package="handler.v1", service_name="MultiRpc")
class MultiRpcController:
    """Controller with multiple RPC method types."""

    @rpc(method_type=RpcMethodType.UNARY)
    async def unary_method(self, request: PingRequest) -> PingReply:
        """Unary RPC."""
        return PingReply(value=request.value)

    @rpc(method_type=RpcMethodType.SERVER_STREAMING, response_type=PingReply)
    async def server_stream_method(
        self, request: PingRequest
    ) -> AsyncGenerator[PingReply, None]:
        """Server streaming RPC."""
        yield PingReply(value=request.value)

    def not_an_rpc(self) -> None:
        """Regular method, not decorated with @rpc."""


def _build_registry_for(controller_type: type) -> DescriptorRegistry:
    """Build and register descriptors for a controller type."""
    registry = DescriptorRegistry()
    file_desc = build_file_descriptor(controller_type)
    registry.register(file_desc)
    return registry


def _make_call_details(method: str) -> MagicMock:
    """Create mock HandlerCallDetails."""
    details = MagicMock(spec=grpc.HandlerCallDetails)
    details.method = method
    return details


@pytest.fixture
def ping_handler() -> GrpcServiceHandler:
    """Create a handler for PingController."""
    registry = _build_registry_for(PingController)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    return GrpcServiceHandler(
        controller_type=PingController,
        package="handler.v1",
        service_name="PingController",
        container=container,
        application_context=application_context,
        registry=registry,
    )


@pytest.fixture
def multi_handler() -> GrpcServiceHandler:
    """Create a handler for MultiRpcController."""
    registry = _build_registry_for(MultiRpcController)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    return GrpcServiceHandler(
        controller_type=MultiRpcController,
        package="handler.v1",
        service_name="MultiRpc",
        container=container,
        application_context=application_context,
        registry=registry,
    )


def test_handler_resolves_known_method(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Handler should return an RpcMethodHandler for a registered method."""
    details = _make_call_details("/handler.v1.PingController/ping")
    result = ping_handler.service(details)
    assert result is not None


def test_handler_returns_none_for_unknown_method(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Handler should return None for an unregistered method."""
    details = _make_call_details("/handler.v1.PingController/nonexistent")
    result = ping_handler.service(details)
    assert result is None


def test_handler_registers_only_rpc_methods(
    multi_handler: GrpcServiceHandler,
) -> None:
    """Handler should register only @rpc-decorated methods."""
    unary_details = _make_call_details("/handler.v1.MultiRpc/unary_method")
    stream_details = _make_call_details("/handler.v1.MultiRpc/server_stream_method")
    plain_details = _make_call_details("/handler.v1.MultiRpc/not_an_rpc")

    assert multi_handler.service(unary_details) is not None
    assert multi_handler.service(stream_details) is not None
    assert multi_handler.service(plain_details) is None


def test_handler_unary_method_has_correct_streaming_flags(
    multi_handler: GrpcServiceHandler,
) -> None:
    """Unary method handler should have both streaming flags as False."""
    details = _make_call_details("/handler.v1.MultiRpc/unary_method")
    handler = multi_handler.service(details)
    assert handler is not None
    assert handler.request_streaming is False
    assert handler.response_streaming is False


def test_handler_server_streaming_method_has_correct_flags(
    multi_handler: GrpcServiceHandler,
) -> None:
    """Server streaming handler should have response_streaming=True."""
    details = _make_call_details("/handler.v1.MultiRpc/server_stream_method")
    handler = multi_handler.service(details)
    assert handler is not None
    assert handler.request_streaming is False
    assert handler.response_streaming is True


async def test_handler_unary_behavior_calls_controller(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Unary handler should invoke the controller method and return result."""
    reply = PingReply(value="pong")
    mock_instance = MagicMock()
    mock_instance.ping = AsyncMock(return_value=reply)
    ping_handler._container.get.return_value = mock_instance

    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None
    assert handler.request_deserializer is not None
    assert handler.unary_unary is not None

    request_class = ping_handler._registry.get_message_class("handler.v1.PingRequest")
    request_msg = json_format.Parse('{"value":"pong"}', request_class())
    raw_bytes = request_msg.SerializeToString()

    deserialized = handler.request_deserializer(raw_bytes)
    context = AsyncMock(spec=grpc.aio.ServicerContext)
    result = await handler.unary_unary(deserialized, context)
    assert result is reply


async def test_handler_serializer_produces_bytes(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Response serializer should produce bytes from a BaseModel."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None
    assert handler.response_serializer is not None

    reply = PingReply(value="hello")
    serialized = handler.response_serializer(reply)
    assert isinstance(serialized, bytes)
    assert len(serialized) > 0


async def test_handler_deserializer_produces_message(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Request deserializer should produce a protobuf Message from bytes."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None
    assert handler.request_deserializer is not None

    request_class = ping_handler._registry.get_message_class("handler.v1.PingRequest")
    msg = json_format.Parse('{"value":"test"}', request_class())
    raw = msg.SerializeToString()

    result = handler.request_deserializer(raw)
    # Round-trip via json_format to verify the serialized message carries
    # the same logical field value as the deserializer output.
    payload = json_format.MessageToJson(
        result,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )
    restored = PingRequest.model_validate_json(payload)
    assert restored.value == "test"


# ------------------------------------------------------------------
# Streaming handler tests
# ------------------------------------------------------------------


@GrpcController(package="stream.v1", service_name="StreamSvc")
class StreamController:
    """Controller with all four streaming patterns."""

    @rpc(method_type=RpcMethodType.CLIENT_STREAMING, request_type=PingRequest)
    async def client_stream(
        self, request_iter: AsyncIterator[PingRequest]
    ) -> PingReply:
        """Client streaming RPC."""
        last = PingReply(value="")
        async for req in request_iter:
            last = PingReply(value=req.value)
        return last

    @rpc(
        method_type=RpcMethodType.BIDI_STREAMING,
        request_type=PingRequest,
        response_type=PingReply,
    )
    async def bidi_stream(
        self, request_iter: AsyncIterator[PingRequest]
    ) -> AsyncGenerator[PingReply, None]:
        """Bidirectional streaming RPC."""
        async for req in request_iter:
            yield PingReply(value=req.value)


@pytest.fixture
def stream_handler() -> GrpcServiceHandler:
    """Create a handler for StreamController."""
    registry = _build_registry_for(StreamController)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    return GrpcServiceHandler(
        controller_type=StreamController,
        package="stream.v1",
        service_name="StreamSvc",
        container=container,
        application_context=application_context,
        registry=registry,
    )


def test_client_streaming_handler_has_correct_flags(
    stream_handler: GrpcServiceHandler,
) -> None:
    """Client streaming handler should have request_streaming=True."""
    details = _make_call_details("/stream.v1.StreamSvc/client_stream")
    handler = stream_handler.service(details)
    assert handler is not None
    assert handler.request_streaming is True
    assert handler.response_streaming is False


def test_bidi_streaming_handler_has_correct_flags(
    stream_handler: GrpcServiceHandler,
) -> None:
    """Bidi streaming handler should have both streaming flags True."""
    details = _make_call_details("/stream.v1.StreamSvc/bidi_stream")
    handler = stream_handler.service(details)
    assert handler is not None
    assert handler.request_streaming is True
    assert handler.response_streaming is True


# ------------------------------------------------------------------
# Serializer / deserializer edge cases
# ------------------------------------------------------------------


async def test_serializer_handles_protobuf_message_directly(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Serializer should pass through if value is already a protobuf Message."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None
    assert handler.response_serializer is not None

    msg_class = ping_handler._registry.get_message_class("handler.v1.PingReply")
    proto_msg = json_format.Parse('{"value":"direct"}', msg_class())
    serialized = handler.response_serializer(proto_msg)
    assert isinstance(serialized, bytes)
    assert serialized == proto_msg.SerializeToString()


async def test_serializer_rejects_unsupported_type(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Serializer should raise when given a non-Message, non-BaseModel object."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None
    assert handler.response_serializer is not None

    with pytest.raises(UnsupportedResponseTypeError) as excinfo:
        handler.response_serializer("not a valid response")
    assert excinfo.value.value_type is str


def test_make_deserializer_returns_none_when_no_request_type() -> None:
    """_make_deserializer should return None when request_type is None."""
    registry = _build_registry_for(PingController)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    handler = GrpcServiceHandler(
        controller_type=PingController,
        package="handler.v1",
        service_name="PingController",
        container=container,
        application_context=application_context,
        registry=registry,
    )
    result = handler._make_deserializer(None)
    assert result is None


def test_make_serializer_returns_none_when_no_response_type() -> None:
    """_make_serializer should return None when response_type is None."""
    registry = _build_registry_for(PingController)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    handler = GrpcServiceHandler(
        controller_type=PingController,
        package="handler.v1",
        service_name="PingController",
        container=container,
        application_context=application_context,
        registry=registry,
    )
    result = handler._make_serializer(None)
    assert result is None


# ------------------------------------------------------------------
# Conversion helpers: _basemodel_to_protobuf / _protobuf_to_basemodel
# ------------------------------------------------------------------


class InnerMsg(BaseModel):
    """Nested message type."""

    text: Annotated[str, ProtoField(number=1)]


class OuterMsg(BaseModel):
    """Message with a nested BaseModel and a repeated field."""

    inner: Annotated[InnerMsg, ProtoField(number=1)]
    tags: Annotated[list[str], ProtoField(number=2)]


@GrpcController(package="nested.v1", service_name="NestedSvc")
class NestedController:
    """Controller using nested/repeated messages."""

    @rpc()
    async def echo(self, request: OuterMsg) -> OuterMsg:
        """Echo nested message."""
        return request


def test_basemodel_to_protobuf_with_nested_and_repeated() -> None:
    """_basemodel_to_protobuf should handle nested BaseModel and repeated fields."""
    registry = _build_registry_for(NestedController)
    msg_class = registry.get_message_class("nested.v1.OuterMsg")

    src = OuterMsg(inner=InnerMsg(text="hi"), tags=["a", "b"])
    proto = _basemodel_to_protobuf(src, msg_class)

    payload = json_format.MessageToJson(proto, preserving_proto_field_name=True)
    restored = OuterMsg.model_validate_json(payload)
    assert restored.inner.text == "hi"
    assert restored.tags == ["a", "b"]


def test_protobuf_to_basemodel_with_nested() -> None:
    """_protobuf_to_basemodel should convert nested messages back to BaseModels."""
    registry = _build_registry_for(NestedController)
    msg_class = registry.get_message_class("nested.v1.OuterMsg")

    proto = json_format.Parse(
        '{"inner":{"text":"world"},"tags":["x"]}',
        msg_class(),
    )

    result = _protobuf_to_basemodel(proto, OuterMsg)
    assert isinstance(result, OuterMsg)
    assert result.inner.text == "world"
    assert result.tags == ["x"]


def test_basemodel_to_protobuf_roundtrip_simple() -> None:
    """Round-trip: BaseModel → protobuf → bytes → protobuf → BaseModel."""
    registry = _build_registry_for(PingController)
    msg_class = registry.get_message_class("handler.v1.PingReply")

    original = PingReply(value="roundtrip")
    proto = _basemodel_to_protobuf(original, msg_class)
    raw = proto.SerializeToString()

    restored_proto = msg_class()
    restored_proto.ParseFromString(raw)
    result = _protobuf_to_basemodel(restored_proto, PingReply)
    assert isinstance(result, PingReply)
    assert result.value == "roundtrip"


# ------------------------------------------------------------------
# Optional field (proto3 optional) round-trip
# ------------------------------------------------------------------


class OptionalMsg(BaseModel):
    """Message with optional fields for HasField testing."""

    name: Annotated[str, ProtoField(number=1)]
    nickname: Annotated[str | None, ProtoField(number=2)] = None


@GrpcController(package="optional.v1", service_name="OptionalSvc")
class OptionalController:
    """Controller using optional fields."""

    @rpc()
    async def echo(self, request: OptionalMsg) -> OptionalMsg:
        """Echo optional message."""
        return request


def test_protobuf_to_basemodel_optional_field_unset_expect_none() -> None:
    """_protobuf_to_basemodel should map unset proto3 optional fields to None."""
    registry = _build_registry_for(OptionalController)
    msg_class = registry.get_message_class("optional.v1.OptionalMsg")

    # nickname is NOT set — json_format omits it; pydantic defaults to None.
    proto = json_format.Parse('{"name":"test"}', msg_class())

    result = _protobuf_to_basemodel(proto, OptionalMsg)
    assert isinstance(result, OptionalMsg)
    assert result.name == "test"
    assert result.nickname is None


def test_protobuf_to_basemodel_optional_field_set_expect_value() -> None:
    """_protobuf_to_basemodel should decode set proto3 optional fields."""
    registry = _build_registry_for(OptionalController)
    msg_class = registry.get_message_class("optional.v1.OptionalMsg")

    proto = json_format.Parse('{"name":"test","nickname":"nick"}', msg_class())

    result = _protobuf_to_basemodel(proto, OptionalMsg)
    assert isinstance(result, OptionalMsg)
    assert result.name == "test"
    assert result.nickname == "nick"


def test_protobuf_to_basemodel_optional_field_set_to_default_expect_default() -> None:
    """_protobuf_to_basemodel should preserve explicitly set default values."""
    registry = _build_registry_for(OptionalController)
    msg_class = registry.get_message_class("optional.v1.OptionalMsg")

    proto = json_format.Parse('{"name":"test","nickname":""}', msg_class())

    result = _protobuf_to_basemodel(proto, OptionalMsg)
    assert isinstance(result, OptionalMsg)
    assert result.nickname == ""


def test_basemodel_to_protobuf_optional_none_roundtrip() -> None:
    """None-valued optional BaseModel fields should round-trip as unset proto fields."""
    registry = _build_registry_for(OptionalController)
    msg_class = registry.get_message_class("optional.v1.OptionalMsg")

    original = OptionalMsg(name="alice", nickname=None)
    proto = _basemodel_to_protobuf(original, msg_class)
    assert proto.HasField("nickname") is False

    restored = _protobuf_to_basemodel(proto, OptionalMsg)
    assert restored.name == "alice"
    assert restored.nickname is None


# ------------------------------------------------------------------
# Repeated message fields (list[BaseModel])
# ------------------------------------------------------------------


class ItemMsg(BaseModel):
    """Repeated element message."""

    label: Annotated[str, ProtoField(number=1)]


class ContainerMsg(BaseModel):
    """Message with a repeated message field."""

    items: Annotated[list[ItemMsg], ProtoField(number=1)]


@GrpcController(package="repeated.v1", service_name="RepeatedSvc")
class RepeatedMsgController:
    """Controller using repeated message fields."""

    @rpc()
    async def echo(self, request: ContainerMsg) -> ContainerMsg:
        """Echo container message."""
        return request


def test_basemodel_to_protobuf_repeated_message_expect_converted() -> None:
    """_basemodel_to_protobuf should convert list[BaseModel] to repeated message."""
    registry = _build_registry_for(RepeatedMsgController)
    msg_class = registry.get_message_class("repeated.v1.ContainerMsg")

    src = ContainerMsg(items=[ItemMsg(label="a"), ItemMsg(label="b")])
    proto = _basemodel_to_protobuf(src, msg_class)

    restored = _protobuf_to_basemodel(proto, ContainerMsg)
    assert len(restored.items) == 2
    assert restored.items[0].label == "a"
    assert restored.items[1].label == "b"


def test_roundtrip_repeated_message_field() -> None:
    """Round-trip: list[BaseModel] → protobuf repeated message → list[BaseModel]."""
    registry = _build_registry_for(RepeatedMsgController)
    msg_class = registry.get_message_class("repeated.v1.ContainerMsg")

    original = ContainerMsg(items=[ItemMsg(label="one"), ItemMsg(label="two")])
    proto = _basemodel_to_protobuf(original, msg_class)
    raw = proto.SerializeToString()

    restored_proto = msg_class()
    restored_proto.ParseFromString(raw)
    result = _protobuf_to_basemodel(restored_proto, ContainerMsg)
    assert isinstance(result, ContainerMsg)
    assert len(result.items) == 2
    assert result.items[0].label == "one"
    assert result.items[1].label == "two"
