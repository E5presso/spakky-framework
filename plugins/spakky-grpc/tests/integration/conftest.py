import threading
import importlib
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable, Generator

import grpc.aio
import pytest
from google.protobuf.message import Message
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.interfaces.service import IService
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.tracing import PLUGIN_NAME as SPAKKY_TRACING_PLUGIN_NAME
import spakky.plugins.grpc

TESTS_ROOT = Path(__file__).resolve().parents[2]
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))


def _serialize_message(message: Message) -> bytes:
    return message.SerializeToString()


def _build_deserializer(
    message_class: type[Message],
) -> Callable[[bytes], Message]:
    def deserialize(payload: bytes) -> Message:
        message = message_class()
        message.ParseFromString(payload)
        return message

    return deserialize


@Pod()
def get_descriptor_registry() -> DescriptorRegistry:
    return DescriptorRegistry()


@Pod()
def get_grpc_server() -> grpc.aio.Server:
    return grpc.aio.server()


@Pod()
class GrpcServerPortBinder(IService):
    """Bind an ephemeral localhost port before the async server starts."""

    _server: grpc.aio.Server
    _stop_event: threading.Event
    address: str
    port: int

    def __init__(self, server: grpc.aio.Server) -> None:
        self._server = server
        self.address = ""
        self.port = 0

    def set_stop_event(self, stop_event: threading.Event) -> None:
        _ = stop_event

    def start(self) -> None:
        self.port = self._server.add_insecure_port("127.0.0.1:0")
        assert self.port != 0
        self.address = f"127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.address = ""
        self.port = 0


@dataclass
class GrpcIntegrationClient:
    """Thin client helper for dynamic runtime protobuf calls."""

    channel: grpc.aio.Channel
    registry: DescriptorRegistry

    def make_message(self, full_name: str, **values: str) -> Message:
        message_class = self.registry.get_message_class(full_name)
        message = message_class()
        for key, value in values.items():
            setattr(message, key, value)  # pyrefly: ignore - runtime protobuf field assignment
        return message

    async def unary_unary(
        self,
        *,
        method_path: str,
        request_full_name: str,
        response_full_name: str,
        metadata: Sequence[tuple[str, str]] | None = None,
        **values: str,
    ) -> tuple[Message, grpc.aio.UnaryUnaryCall]:
        response_class = self.registry.get_message_class(response_full_name)
        call = self.channel.unary_unary(
            method_path,
            request_serializer=_serialize_message,
            response_deserializer=_build_deserializer(response_class),
        )(
            self.make_message(request_full_name, **values),
            metadata=metadata,
        )
        response = await call
        return response, call

    async def unary_stream(
        self,
        *,
        method_path: str,
        request_full_name: str,
        response_full_name: str,
        metadata: Sequence[tuple[str, str]] | None = None,
        **values: str,
    ) -> tuple[list[Message], grpc.aio.UnaryStreamCall]:
        response_class = self.registry.get_message_class(response_full_name)
        call = self.channel.unary_stream(
            method_path,
            request_serializer=_serialize_message,
            response_deserializer=_build_deserializer(response_class),
        )(
            self.make_message(request_full_name, **values),
            metadata=metadata,
        )
        responses = [item async for item in call]
        return responses, call

    async def stream_unary(
        self,
        *,
        method_path: str,
        request_full_name: str,
        response_full_name: str,
        request_values: Sequence[dict[str, str]],
        metadata: Sequence[tuple[str, str]] | None = None,
    ) -> tuple[Message, grpc.aio.StreamUnaryCall]:
        response_class = self.registry.get_message_class(response_full_name)

        async def request_iterator() -> AsyncGenerator[Message, None]:
            for values in request_values:
                yield self.make_message(request_full_name, **values)

        call = self.channel.stream_unary(
            method_path,
            request_serializer=_serialize_message,
            response_deserializer=_build_deserializer(response_class),
        )(
            request_iterator(),
            metadata=metadata,
        )
        response = await call
        return response, call

    async def stream_stream(
        self,
        *,
        method_path: str,
        request_full_name: str,
        response_full_name: str,
        request_values: Sequence[dict[str, str]],
        metadata: Sequence[tuple[str, str]] | None = None,
    ) -> tuple[list[Message], grpc.aio.StreamStreamCall]:
        response_class = self.registry.get_message_class(response_full_name)

        async def request_iterator() -> AsyncGenerator[Message, None]:
            for values in request_values:
                yield self.make_message(request_full_name, **values)

        call = self.channel.stream_stream(
            method_path,
            request_serializer=_serialize_message,
            response_deserializer=_build_deserializer(response_class),
        )(
            request_iterator(),
            metadata=metadata,
        )
        responses = [item async for item in call]
        return responses, call


@pytest.fixture(name="app", scope="function")
def get_app_fixture() -> Generator[SpakkyApplication, None, None]:
    apps = importlib.import_module("tests.integration.apps")
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.plugins.grpc.PLUGIN_NAME,
                SPAKKY_TRACING_PLUGIN_NAME,
            }
        )
        .scan(apps)
        .add(get_descriptor_registry)
        .add(get_grpc_server)
        .add(GrpcServerPortBinder)
    )
    app.start()

    yield app

    app.stop()


@pytest.fixture(name="channel", scope="function")
async def get_channel_fixture(
    app: SpakkyApplication,
) -> AsyncGenerator[grpc.aio.Channel, None]:
    binder = app.container.get(GrpcServerPortBinder)
    async with grpc.aio.insecure_channel(binder.address) as channel:
        yield channel


@pytest.fixture(name="grpc_client", scope="function")
def get_grpc_client_fixture(
    app: SpakkyApplication,
    channel: grpc.aio.Channel,
) -> GrpcIntegrationClient:
    registry = app.container.get(DescriptorRegistry)
    return GrpcIntegrationClient(channel=channel, registry=registry)
