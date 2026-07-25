"""Integration tests for unary RPC dispatch over a live ``grpc.aio.Server``."""

import grpc.aio
import pytest

from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.codec import deserializer_for, serializer_for
from tests.integration.apps.echo import (
    EchoReply,
    EchoRequest,
    ProfileReply,
    ProfileRequest,
)

PACKAGE = "test.echo"
SERVICE_METHOD = "/test.echo.EchoController/unary_echo"
PROFILE_METHOD = "/test.echo.EchoController/echo_profile"


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


@pytest.mark.asyncio
async def test_echo_profile_zero_config_multi_field_expect_roundtrip(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """A multi-field zero-config message should roundtrip every field intact.

    ``ProfileRequest``/``ProfileReply`` carry no ``ProtoField`` annotations,
    so client and server derive each field number from the field name hash.
    A correct roundtrip across distinct types (str/int/bool) proves the
    derived numbering is symmetric on both sides of the wire.
    """
    call = channel.unary_unary(
        PROFILE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.ProfileRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.ProfileReply", ProfileReply
        ),
    )
    reply = await call(ProfileRequest(nickname="spakky", age=7, verified=True))

    assert isinstance(reply, ProfileReply)
    assert reply.nickname == "spakky"
    assert reply.age == 7
    assert reply.verified is True
