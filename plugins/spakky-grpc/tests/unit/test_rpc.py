"""Unit tests for @rpc decorator."""

from dataclasses import dataclass
from typing import AsyncIterator

from spakky.plugins.grpc.decorators.rpc import Rpc, RpcMethodType, rpc


@dataclass
class HelloRequest:
    name: str


@dataclass
class HelloResponse:
    message: str


def test_rpc_default_method_type_is_unary() -> None:
    """@rpc() should default to UNARY method type."""

    @rpc()
    async def say_hello(self: object, request: HelloRequest) -> HelloResponse:
        """Say hello."""
        ...

    annotation = Rpc.get(say_hello)
    assert annotation.method_type == RpcMethodType.UNARY


def test_rpc_server_streaming_method_type() -> None:
    """@rpc(method_type=SERVER_STREAMING) should store server streaming type."""

    @rpc(method_type=RpcMethodType.SERVER_STREAMING)
    async def list_features(
        self: object, request: HelloRequest
    ) -> AsyncIterator[HelloResponse]:
        """List features."""
        ...

    annotation = Rpc.get(list_features)
    assert annotation.method_type == RpcMethodType.SERVER_STREAMING


def test_rpc_client_streaming_method_type() -> None:
    """@rpc(method_type=CLIENT_STREAMING) should store client streaming type."""

    @rpc(method_type=RpcMethodType.CLIENT_STREAMING)
    async def record_route(
        self: object, requests: AsyncIterator[HelloRequest]
    ) -> HelloResponse:
        """Record route."""
        ...

    annotation = Rpc.get(record_route)
    assert annotation.method_type == RpcMethodType.CLIENT_STREAMING


def test_rpc_bidi_streaming_method_type() -> None:
    """@rpc(method_type=BIDI_STREAMING) should store bidi streaming type."""

    @rpc(method_type=RpcMethodType.BIDI_STREAMING)
    async def route_chat(
        self: object, requests: AsyncIterator[HelloRequest]
    ) -> AsyncIterator[HelloResponse]:
        """Route chat."""
        ...

    annotation = Rpc.get(route_chat)
    assert annotation.method_type == RpcMethodType.BIDI_STREAMING


def test_rpc_extracts_request_type_from_hints() -> None:
    """@rpc() should auto-extract request type from type hints."""

    @rpc()
    async def say_hello(self: object, request: HelloRequest) -> HelloResponse:
        """Say hello."""
        ...

    annotation = Rpc.get(say_hello)
    assert annotation.request_type is HelloRequest


def test_rpc_extracts_response_type_from_hints() -> None:
    """@rpc() should auto-extract response type from return type hint."""

    @rpc()
    async def say_hello(self: object, request: HelloRequest) -> HelloResponse:
        """Say hello."""
        ...

    annotation = Rpc.get(say_hello)
    assert annotation.response_type is HelloResponse


def test_rpc_uses_explicit_request_type() -> None:
    """@rpc() should use explicitly provided request type."""

    @rpc(request_type=HelloRequest)
    async def say_hello(self: object, request: object) -> HelloResponse:
        """Say hello."""
        ...

    annotation = Rpc.get(say_hello)
    assert annotation.request_type is HelloRequest


def test_rpc_uses_explicit_response_type() -> None:
    """@rpc() should use explicitly provided response type."""

    @rpc(response_type=HelloResponse)
    async def say_hello(self: object, request: HelloRequest) -> object:
        """Say hello."""
        ...

    annotation = Rpc.get(say_hello)
    assert annotation.response_type is HelloResponse


def test_rpc_annotation_exists_check() -> None:
    """Rpc.exists() should return True for annotated methods."""

    @rpc()
    async def say_hello(self: object, request: HelloRequest) -> HelloResponse:
        """Say hello."""
        ...

    assert Rpc.exists(say_hello)


def test_rpc_annotation_not_exists_for_plain_method() -> None:
    """Rpc.exists() should return False for non-annotated methods."""

    async def say_hello(self: object, request: HelloRequest) -> HelloResponse:
        """Say hello."""
        ...

    assert not Rpc.exists(say_hello)


def test_rpc_no_params_returns_none_for_request_type() -> None:
    """@rpc() on a method with no params should set request_type to None."""

    @rpc()
    async def health_check() -> HelloResponse:
        """Health check."""
        ...

    annotation = Rpc.get(health_check)
    assert annotation.request_type is None
