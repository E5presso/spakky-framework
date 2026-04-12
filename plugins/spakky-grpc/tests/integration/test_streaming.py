"""Integration tests covering server/client/bidirectional streaming RPCs."""

from collections.abc import AsyncIterator

import grpc.aio
import pytest

from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from tests.integration._client import deserializer_for, serializer_for
from tests.integration.apps.echo import CountReply, CountRequest, EchoReply, EchoRequest

PACKAGE = "test.echo"


@pytest.mark.asyncio
async def test_server_streaming_with_count_three_expect_three_replies(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """server_streaming_count should emit exactly ``count`` replies."""
    call = channel.unary_stream(
        "/test.echo.EchoController/server_streaming_count",
        request_serializer=serializer_for(registry, f"{PACKAGE}.CountRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )
    replies: list[str] = []
    async for reply in call(CountRequest(count=3)):
        assert isinstance(reply, EchoReply)
        replies.append(reply.text)

    assert replies == ["item-0", "item-1", "item-2"]


@pytest.mark.asyncio
async def test_client_streaming_with_three_requests_expect_summed_total(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """client_streaming_sum should aggregate every inbound ``count`` field."""
    call = channel.stream_unary(
        "/test.echo.EchoController/client_streaming_sum",
        request_serializer=serializer_for(registry, f"{PACKAGE}.CountRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.CountReply", CountReply
        ),
    )

    async def _requests() -> AsyncIterator[CountRequest]:
        for value in (1, 2, 3):
            yield CountRequest(count=value)

    reply = await call(_requests())

    assert isinstance(reply, CountReply)
    assert reply.total == 6


@pytest.mark.asyncio
async def test_bidi_streaming_with_three_messages_expect_echo_in_order(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """bidi_streaming_echo should echo each request preserving order."""
    call = channel.stream_stream(
        "/test.echo.EchoController/bidi_streaming_echo",
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )

    sent = ["alpha", "beta", "gamma"]

    async def _requests() -> AsyncIterator[EchoRequest]:
        for text in sent:
            yield EchoRequest(text=text)

    stream = call(_requests())
    received: list[str] = []
    async for reply in stream:
        assert isinstance(reply, EchoReply)
        received.append(reply.text)

    assert received == sent
