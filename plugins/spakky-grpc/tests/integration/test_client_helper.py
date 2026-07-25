"""Integration tests calling a live server through the shipped client helper."""

from collections.abc import AsyncIterator

import grpc.aio
import pytest
from spakky.plugins.grpc.client import GrpcClient
from spakky.plugins.grpc.schema.registry import DescriptorRegistry

from tests.integration.apps.echo import (
    CountRequest,
    EchoController,
    EchoReply,
    EchoRequest,
    ProfileRequest,
)


@pytest.fixture(name="client")
def get_client_fixture(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> GrpcClient:
    """Build a client for the echo service sharing the server's descriptor pool."""
    return GrpcClient(channel, EchoController, registry)


@pytest.mark.asyncio
async def test_unary_unary_through_client_expect_same_text(client: GrpcClient) -> None:
    """The client should call a unary method and decode the reply model."""
    reply = await client.unary_unary(EchoController.unary_echo)(EchoRequest(text="hi"))

    assert isinstance(reply, EchoReply)
    assert reply.text == "hi"


@pytest.mark.asyncio
async def test_unary_stream_through_client_expect_numbered_items(
    client: GrpcClient,
) -> None:
    """The client should iterate a server-streaming method's replies."""
    call = client.unary_stream(EchoController.server_streaming_count)(
        CountRequest(count=3)
    )

    assert [reply.text async for reply in call] == ["item-0", "item-1", "item-2"]


@pytest.mark.asyncio
async def test_stream_unary_through_client_expect_summed_total(
    client: GrpcClient,
) -> None:
    """The client should stream requests into a client-streaming method."""

    async def _counts() -> AsyncIterator[CountRequest]:
        for count in (1, 2, 3):
            yield CountRequest(count=count)

    reply = await client.stream_unary(EchoController.client_streaming_sum)(_counts())

    assert reply.total == 6


@pytest.mark.asyncio
async def test_stream_stream_through_client_expect_echoed_items(
    client: GrpcClient,
) -> None:
    """The client should exchange messages with a bidirectional method."""

    async def _texts() -> AsyncIterator[EchoRequest]:
        for text in ("a", "b"):
            yield EchoRequest(text=text)

    call = client.stream_stream(EchoController.bidi_streaming_echo)(_texts())

    assert [reply.text async for reply in call] == ["a", "b"]


@pytest.mark.asyncio
async def test_client_with_private_registry_expect_matching_wire_layout(
    channel: grpc.aio.Channel,
) -> None:
    """A client compiling its own descriptors must still agree on the wire layout.

    This is the case the helper exists for: the caller never touches the
    server's registry, so every field number has to come from the same
    controller declaration instead of a second hand-written copy of the models.
    """
    client = GrpcClient(channel, EchoController)

    reply = await client.unary_unary(EchoController.echo_profile)(
        ProfileRequest(nickname="spakky", age=30, verified=True)
    )

    assert (reply.nickname, reply.age, reply.verified) == ("spakky", 30, True)
