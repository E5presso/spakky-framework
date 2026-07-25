"""Unit tests for the typed client built from a @GrpcController declaration."""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import cast
from unittest.mock import MagicMock

import grpc.aio
import pytest
from pydantic import BaseModel
from spakky.plugins.grpc.client import GrpcClient
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.error import (
    MessagelessRpcMethodError,
    NotAnRpcMethodError,
    RpcMethodTypeMismatchError,
)
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

from tests.unit.conftest import GreeterController, HelloRequest

GREETER_FILE_NAME = "test/v1/GreeterController.proto"
GREETER_SERVICE_NAME = "test.v1.GreeterController"
SAY_HELLO_METHOD = "/test.v1.GreeterController/say_hello"


class Beat(BaseModel):
    """Message used by the heartbeat methods under test."""

    value: str


@GrpcController(package="client.v1")
class HeartbeatController:
    """Controller exposing every streaming pattern the client can address."""

    @rpc(
        method_type=RpcMethodType.SERVER_STREAMING,
        request_type=Beat,
        response_type=Beat,
    )
    async def watch(self, request: Beat) -> AsyncIterator[Beat]:
        """Stream beats back to the caller."""
        yield request

    @rpc(
        method_type=RpcMethodType.CLIENT_STREAMING,
        request_type=Beat,
        response_type=Beat,
    )
    async def collect(self, requests: AsyncIterator[Beat]) -> Beat:
        """Fold inbound beats into one reply."""
        return [beat async for beat in requests][-1]

    @rpc(
        method_type=RpcMethodType.BIDI_STREAMING,
        request_type=Beat,
        response_type=Beat,
    )
    async def exchange(self, requests: AsyncIterator[Beat]) -> AsyncIterator[Beat]:
        """Echo every inbound beat."""
        async for beat in requests:
            yield beat

    @rpc(
        method_type=RpcMethodType.SERVER_STREAMING,
        request_type=Beat,
        response_type=Beat,
    )
    async def mislabelled(self, request: Beat) -> Beat:
        """Unary-shaped method annotated as server streaming."""
        return request

    async def not_exposed(self, request: Beat) -> Beat:
        """Plain method that was never decorated with @rpc."""
        return request


class RequestLessMethods:
    """Holder for an @rpc method that declares no request model.

    It carries no ``@GrpcController`` stereotype because such a method cannot
    be compiled into a descriptor at all — protobuf has no empty input type.
    """

    @rpc()
    async def ping(self) -> Beat:
        """RPC taking no request message."""
        return Beat(value="pong")


@pytest.fixture(name="channel")
def get_channel_fixture() -> MagicMock:
    """Create a stand-in channel recording the multicallable arguments."""
    return MagicMock(spec=grpc.aio.Channel)


def test_client_registers_controller_descriptor_in_registry(
    channel: MagicMock,
) -> None:
    """Constructing the client compiles the controller's descriptor."""
    registry = DescriptorRegistry()

    GrpcClient(channel, GreeterController, registry)

    assert registry.is_registered(GREETER_FILE_NAME)


def test_client_with_prepopulated_registry_expect_no_duplicate_registration(
    channel: MagicMock,
) -> None:
    """Sharing a registry with a running server must not re-register the schema."""
    registry = DescriptorRegistry()
    GrpcClient(channel, GreeterController, registry)

    GrpcClient(channel, GreeterController, registry)

    assert registry.service_names == (GREETER_SERVICE_NAME,)


def test_client_without_registry_expect_private_registry(channel: MagicMock) -> None:
    """Omitting the registry gives the client its own compiled descriptor pool."""
    client = GrpcClient(channel, GreeterController)

    assert client.registry.is_registered(GREETER_FILE_NAME)


def test_unary_unary_expect_full_method_path(channel: MagicMock) -> None:
    """The callable should address the method by its fully-qualified path."""
    client = GrpcClient(channel, GreeterController)

    client.unary_unary(GreeterController.say_hello)

    assert channel.unary_unary.call_args.args[0] == SAY_HELLO_METHOD


def test_unary_unary_expect_codecs_matching_declared_models(
    channel: MagicMock,
) -> None:
    """The codecs should round-trip the models the controller declares."""
    client = GrpcClient(channel, GreeterController)

    client.unary_unary(GreeterController.say_hello)

    serialize = channel.unary_unary.call_args.kwargs["request_serializer"]
    deserialize = channel.unary_unary.call_args.kwargs["response_deserializer"]
    assert deserialize(serialize(HelloRequest(name="spakky"))).message == "spakky"


def test_unary_stream_expect_server_streaming_callable(channel: MagicMock) -> None:
    """A server-streaming method should be addressed through unary_stream."""
    client = GrpcClient(channel, HeartbeatController)

    client.unary_stream(HeartbeatController.watch)

    assert (
        channel.unary_stream.call_args.args[0] == "/client.v1.HeartbeatController/watch"
    )


def test_stream_unary_expect_client_streaming_callable(channel: MagicMock) -> None:
    """A client-streaming method should be addressed through stream_unary."""
    client = GrpcClient(channel, HeartbeatController)

    client.stream_unary(HeartbeatController.collect)

    assert (
        channel.stream_unary.call_args.args[0]
        == "/client.v1.HeartbeatController/collect"
    )


def test_stream_stream_expect_bidi_streaming_callable(channel: MagicMock) -> None:
    """A bidirectional method should be addressed through stream_stream."""
    client = GrpcClient(channel, HeartbeatController)

    client.stream_stream(HeartbeatController.exchange)

    assert (
        channel.stream_stream.call_args.args[0]
        == "/client.v1.HeartbeatController/exchange"
    )


def test_unary_unary_on_undecorated_method_expect_error(channel: MagicMock) -> None:
    """Referencing a method without @rpc must fail instead of calling a dead path."""
    client = GrpcClient(channel, HeartbeatController)

    with pytest.raises(NotAnRpcMethodError):
        client.unary_unary(HeartbeatController.not_exposed)


def test_unary_unary_on_streaming_method_expect_error(channel: MagicMock) -> None:
    """Requesting the wrong streaming shape must fail before the call is made."""
    client = GrpcClient(channel, HeartbeatController)

    with pytest.raises(RpcMethodTypeMismatchError):
        client.unary_unary(HeartbeatController.mislabelled)


def test_unary_unary_on_request_less_method_expect_error(channel: MagicMock) -> None:
    """A method declaring no request model cannot be addressed over the wire."""
    client = GrpcClient(channel, HeartbeatController)
    # The typed signature already rejects a request-less method; the cast reaches the
    # runtime guard that untyped callers would otherwise hit as an AttributeError.
    request_less = cast(
        Callable[[RequestLessMethods, Beat], Coroutine[object, object, Beat]],
        RequestLessMethods.ping,
    )

    with pytest.raises(MessagelessRpcMethodError):
        client.unary_unary(request_less)
