"""Integration tests for gRPC method shapes and interceptor behavior."""

from collections.abc import AsyncIterator

import grpc
import pytest
from google.protobuf.message import Message
from spakky.tracing.context import TraceContext


def _to_wire(message: Message) -> bytes:
    """Serialize a dynamic protobuf message to wire bytes."""
    return message.SerializeToString()


async def _numbers(
    number_cls: type,
    values: list[int],
) -> AsyncIterator[Message]:
    """Build an async request stream from integers."""
    for value in values:
        yield number_cls(value=value)


async def _messages(
    message_cls: type,
    values: list[str],
) -> AsyncIterator[Message]:
    """Build an async request stream from strings."""
    for value in values:
        yield message_cls(message=value)


async def test_unary_roundtrip(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Unary RPC should return dataclass-mapped response payload."""
    stub = grpc_channel.unary_unary(
        "/itest.v1.IntegrationService/unary_echo",
        request_serializer=_to_wire,
        response_deserializer=message_types["EchoReply"].FromString,
    )

    response = await stub(message_types["EchoRequest"](message="hello"))

    assert response.message == "hello"


async def test_server_streaming_roundtrip(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Server-streaming RPC should yield all streamed responses."""
    stub = grpc_channel.unary_stream(
        "/itest.v1.IntegrationService/stream_count",
        request_serializer=_to_wire,
        response_deserializer=message_types["EchoReply"].FromString,
    )

    call = stub(message_types["CountRequest"](count=3))
    responses = [item.message async for item in call]

    assert responses == ["item-0", "item-1", "item-2"]


async def test_client_streaming_roundtrip(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Client-streaming RPC should aggregate stream values."""
    stub = grpc_channel.stream_unary(
        "/itest.v1.IntegrationService/sum_stream",
        request_serializer=_to_wire,
        response_deserializer=message_types["SumReply"].FromString,
    )

    response = await stub(_numbers(message_types["NumberChunk"], [3, 4, 5]))

    assert response.total == 12


async def test_bidi_streaming_roundtrip(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Bidi-streaming RPC should echo each inbound message."""
    stub = grpc_channel.stream_stream(
        "/itest.v1.IntegrationService/chat",
        request_serializer=_to_wire,
        response_deserializer=message_types["EchoReply"].FromString,
    )

    call = stub(_messages(message_types["EchoRequest"], ["a", "b"]))
    responses = [item.message async for item in call]

    assert responses == ["echo:a", "echo:b"]


async def test_error_mapping_to_grpc_status(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Domain gRPC error should be mapped to expected status code."""
    stub = grpc_channel.unary_unary(
        "/itest.v1.IntegrationService/fail_not_found",
        request_serializer=_to_wire,
        response_deserializer=message_types["EchoReply"].FromString,
    )

    with pytest.raises(grpc.aio.AioRpcError) as exception_info:
        await stub(message_types["FailRequest"](resource_id="missing"))

    assert exception_info.value.code() == grpc.StatusCode.NOT_FOUND
    assert exception_info.value.details() == "Not Found"


async def test_tracing_interceptor_extracts_and_injects_context(
    grpc_channel: grpc.aio.Channel,
    message_types: dict[str, type],
) -> None:
    """Tracing interceptor should extract inbound and inject trailing context."""
    parent = TraceContext.new_root()
    stub = grpc_channel.unary_unary(
        "/itest.v1.IntegrationService/unary_echo",
        request_serializer=_to_wire,
        response_deserializer=message_types["EchoReply"].FromString,
    )

    call = stub(
        message_types["EchoRequest"](message="trace"),
        metadata=(("traceparent", parent.to_traceparent()),),
    )
    response = await call

    assert response.message == "trace"
    trailing = dict(await call.trailing_metadata() or [])
    assert "traceparent" in trailing
    traceparent = trailing["traceparent"]
    if isinstance(traceparent, bytes):
        traceparent = traceparent.decode("utf-8")
    extracted = TraceContext.from_traceparent(traceparent)
    assert extracted.trace_id == parent.trace_id
    assert extracted.span_id != parent.span_id
    assert TraceContext.get() is None
