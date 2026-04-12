"""Integration tests covering server/client/bidirectional streaming RPCs."""

from collections.abc import AsyncIterator

from google.protobuf.message import Message

import grpc.aio
import pytest

from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from tests.integration._client import (
    build_message,
    deserializer_for,
    field,
    serializer_for,
)

PACKAGE = "test.echo"


@pytest.mark.asyncio
async def test_server_streaming_with_count_three_expect_three_replies(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """server_streaming_count should emit exactly ``count`` replies."""
    call = channel.unary_stream(
        "/test.echo.EchoController/server_streaming_count",
        request_serializer=serializer_for(registry, f"{PACKAGE}.CountRequest"),
        response_deserializer=deserializer_for(registry, f"{PACKAGE}.EchoReply"),
    )
    request = build_message(registry, f"{PACKAGE}.CountRequest", count=3)

    replies: list[object] = []
    async for reply in call(request):
        replies.append(field(reply, "text"))

    assert replies == ["item-0", "item-1", "item-2"]


@pytest.mark.asyncio
async def test_client_streaming_with_three_requests_expect_summed_total(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """client_streaming_sum should aggregate every inbound ``count`` field."""
    call = channel.stream_unary(
        "/test.echo.EchoController/client_streaming_sum",
        request_serializer=serializer_for(registry, f"{PACKAGE}.CountRequest"),
        response_deserializer=deserializer_for(registry, f"{PACKAGE}.CountReply"),
    )

    async def _requests() -> AsyncIterator[Message]:
        for value in (1, 2, 3):
            yield build_message(registry, f"{PACKAGE}.CountRequest", count=value)

    reply = await call(_requests())

    assert field(reply, "total") == 6


@pytest.mark.asyncio
async def test_bidi_streaming_with_three_messages_expect_echo_in_order(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """bidi_streaming_echo should echo each request preserving order."""
    call = channel.stream_stream(
        "/test.echo.EchoController/bidi_streaming_echo",
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(registry, f"{PACKAGE}.EchoReply"),
    )

    sent = ["alpha", "beta", "gamma"]

    async def _requests() -> AsyncIterator[Message]:
        for text in sent:
            yield build_message(registry, f"{PACKAGE}.EchoRequest", text=text)

    stream = call(_requests())
    received: list[object] = []
    async for reply in stream:
        received.append(field(reply, "text"))

    assert received == sent
