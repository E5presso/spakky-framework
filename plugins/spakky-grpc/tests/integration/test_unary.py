"""Integration tests for unary RPC dispatch over a live ``grpc.aio.Server``."""

import grpc.aio
import pytest

from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from tests.integration._client import deserializer_for, serializer_for
from tests.integration.apps.echo import EchoReply, EchoRequest

PACKAGE = "test.echo"
SERVICE_METHOD = "/test.echo.EchoController/unary_echo"


@pytest.mark.asyncio
async def test_unary_echo_with_text_expect_same_text(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """unary_echo should return an EchoReply with the request text unchanged."""
    call = channel.unary_unary(
        SERVICE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )
    reply = await call(EchoRequest(text="hello"))

    assert isinstance(reply, EchoReply)
    assert reply.text == "hello"


@pytest.mark.asyncio
async def test_unary_echo_with_empty_text_expect_empty_reply(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """unary_echo should preserve empty strings as protobuf default values."""
    call = channel.unary_unary(
        SERVICE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )
    reply = await call(EchoRequest(text=""))

    assert isinstance(reply, EchoReply)
    assert reply.text == ""
