"""Unit tests for GrpcServiceHandler."""

from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import grpc
import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.handler import (
    GrpcServiceHandler,
    _convert_proto_value,
    _dataclass_to_protobuf,
    _protobuf_to_dataclass,
)
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class PingRequest:
    """Test request."""

    value: Annotated[str, ProtoField(number=1)]


@dataclass
class PingReply:
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
        yield PingReply(value=request.value)  # type: ignore[misc] — async generator for test

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

    request_class = ping_handler._registry.get_message_class("handler.v1.PingRequest")
    request_msg = request_class()
    request_msg.value = "pong"  # pyrefly: ignore - dynamic protobuf attr
    raw_bytes = request_msg.SerializeToString()

    deserialized = handler.request_deserializer(  # pyrefly: ignore - callable at runtime after service() lookup
        raw_bytes
    )
    context = AsyncMock(spec=grpc.aio.ServicerContext)
    result = await handler.unary_unary(  # pyrefly: ignore - callable at runtime after service() lookup
        deserialized, context
    )
    assert result is not None


async def test_handler_serializer_produces_bytes(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Response serializer should produce bytes from a dataclass."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None

    reply = PingReply(value="hello")
    serialized = handler.response_serializer(  # pyrefly: ignore - callable at runtime after service() lookup
        reply
    )
    assert isinstance(serialized, bytes)
    assert len(serialized) > 0


async def test_handler_deserializer_produces_message(
    ping_handler: GrpcServiceHandler,
) -> None:
    """Request deserializer should produce a protobuf Message from bytes."""
    details = _make_call_details("/handler.v1.PingController/ping")
    handler = ping_handler.service(details)
    assert handler is not None

    request_class = ping_handler._registry.get_message_class("handler.v1.PingRequest")
    msg = request_class()
    msg.value = "test"  # pyrefly: ignore - dynamic protobuf attr
    raw = msg.SerializeToString()

    result = handler.request_deserializer(  # pyrefly: ignore - callable at runtime after service() lookup
        raw
    )
    assert hasattr(result, "value")
    assert result.value == "test"


# ------------------------------------------------------------------
# Streaming handler tests (cover CLIENT_STREAMING and BIDI_STREAMING)
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

    msg_class = ping_handler._registry.get_message_class("handler.v1.PingReply")
    proto_msg = msg_class()
    proto_msg.value = "direct"  # pyrefly: ignore - dynamic protobuf attr
    serialized = handler.response_serializer(  # pyrefly: ignore - callable at runtime after service() lookup
        proto_msg
    )
    assert isinstance(serialized, bytes)


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
# Conversion helpers: _dataclass_to_protobuf / _protobuf_to_dataclass
# ------------------------------------------------------------------


@dataclass
class InnerMsg:
    """Nested message type."""

    text: Annotated[str, ProtoField(number=1)]


@dataclass
class OuterMsg:
    """Message with a nested dataclass and a repeated field."""

    inner: Annotated[InnerMsg, ProtoField(number=1)]
    tags: Annotated[list[str], ProtoField(number=2)]


@GrpcController(package="nested.v1", service_name="NestedSvc")
class NestedController:
    """Controller using nested/repeated messages."""

    @rpc()
    async def echo(self, request: OuterMsg) -> OuterMsg:
        """Echo nested message."""
        return request


def test_dataclass_to_protobuf_with_nested_and_repeated() -> None:
    """_dataclass_to_protobuf should handle nested dataclass and repeated fields."""
    registry = _build_registry_for(NestedController)
    msg_class = registry.get_message_class("nested.v1.OuterMsg")

    src = OuterMsg(inner=InnerMsg(text="hi"), tags=["a", "b"])
    proto = _dataclass_to_protobuf(src, msg_class)

    assert proto.inner.text == "hi"  # pyrefly: ignore - dynamic protobuf attr
    assert list(proto.tags) == ["a", "b"]  # pyrefly: ignore - dynamic protobuf attr


def test_protobuf_to_dataclass_with_nested() -> None:
    """_protobuf_to_dataclass should convert nested messages back to dataclasses."""
    registry = _build_registry_for(NestedController)
    msg_class = registry.get_message_class("nested.v1.OuterMsg")

    proto = msg_class()
    proto.inner.text = "world"  # pyrefly: ignore - dynamic protobuf attr
    proto.tags.append("x")  # pyrefly: ignore - dynamic protobuf attr

    result = _protobuf_to_dataclass(proto, OuterMsg)
    assert isinstance(result, OuterMsg)


def test_dataclass_to_protobuf_roundtrip_simple() -> None:
    """Round-trip: dataclass → protobuf → bytes → protobuf → dataclass."""
    registry = _build_registry_for(PingController)
    msg_class = registry.get_message_class("handler.v1.PingReply")

    original = PingReply(value="roundtrip")
    proto = _dataclass_to_protobuf(original, msg_class)
    raw = proto.SerializeToString()

    restored_proto = msg_class()
    restored_proto.ParseFromString(raw)
    result = _protobuf_to_dataclass(restored_proto, PingReply)
    assert isinstance(result, PingReply)
    assert result.value == "roundtrip"


# ------------------------------------------------------------------
# Edge case: _convert_proto_value with nested Message + dataclass type
# ------------------------------------------------------------------


def test_convert_proto_value_nested_message_to_dataclass() -> None:
    """_convert_proto_value should convert nested Message to dataclass."""
    registry = _build_registry_for(NestedController)
    outer_class = registry.get_message_class("nested.v1.OuterMsg")

    proto = outer_class()
    proto.inner.text = "nested"  # pyrefly: ignore - dynamic protobuf attr

    inner_message = proto.inner  # pyrefly: ignore - dynamic protobuf attr
    result = _convert_proto_value(inner_message, InnerMsg)
    assert isinstance(result, InnerMsg)
    assert result.text == "nested"


# ------------------------------------------------------------------
# Edge case: _dataclass_to_protobuf with None fields
# ------------------------------------------------------------------


def test_dataclass_to_protobuf_skips_none_fields() -> None:
    """_dataclass_to_protobuf should skip fields when getattr returns None."""
    registry = _build_registry_for(PingController)
    msg_class = registry.get_message_class("handler.v1.PingReply")

    # Create an object whose 'value' field returns None
    mock_obj = MagicMock()
    mock_obj.value = None

    proto = _dataclass_to_protobuf(mock_obj, msg_class)
    # Default proto3 value for string is ""
    assert proto.value == ""  # pyrefly: ignore - dynamic protobuf attr
