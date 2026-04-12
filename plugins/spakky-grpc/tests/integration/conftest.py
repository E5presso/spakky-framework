"""Integration-test fixtures booting a real ``grpc.aio.Server`` per test."""

import socket
from collections.abc import AsyncIterator, Iterator

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

import spakky.plugins.grpc
import spakky.tracing
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from tests.integration import apps


def _reserve_port() -> int:
    """Ask the OS for an unused localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _build_app(port: int, *, with_tracing: bool) -> SpakkyApplication:
    """Build and start a SpakkyApplication with the grpc plugin loaded."""
    plugins = {spakky.plugins.grpc.PLUGIN_NAME}
    if with_tracing:
        plugins.add(spakky.tracing.PLUGIN_NAME)

    @Pod(name="grpc_server_spec")
    def get_spec() -> GrpcServerSpec:
        spec = GrpcServerSpec()
        spec.add_insecure_port(f"127.0.0.1:{port}")
        return spec

    @Pod(name="descriptor_registry")
    def get_registry() -> DescriptorRegistry:
        return DescriptorRegistry()

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include=plugins)
        .scan(apps)
        .add(get_spec)
        .add(get_registry)
    )
    app.start()
    return app


@pytest.fixture(name="port")
def get_port_fixture() -> int:
    """Return a free localhost port for a single test."""
    return _reserve_port()


@pytest.fixture(name="app")
def get_app_fixture(port: int) -> Iterator[SpakkyApplication]:
    """Boot a SpakkyApplication with tracing enabled and tear it down afterwards."""
    app = _build_app(port, with_tracing=True)
    try:
        yield app
    finally:
        app.stop()


@pytest.fixture(name="app_without_tracing")
def get_app_without_tracing_fixture(port: int) -> Iterator[SpakkyApplication]:
    """Boot a SpakkyApplication with only the gRPC plugin (no tracing)."""
    app = _build_app(port, with_tracing=False)
    try:
        yield app
    finally:
        app.stop()


@pytest_asyncio.fixture(name="channel")
async def get_channel_fixture(
    app: SpakkyApplication, port: int
) -> AsyncIterator[grpc.aio.Channel]:
    """Open an insecure channel against the running test server."""
    del app  # the fixture keeps the server alive for the duration of the test
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield channel
    finally:
        await channel.close()


@pytest.fixture(name="registry")
def get_registry_fixture(app: SpakkyApplication) -> DescriptorRegistry:
    """Expose the ``DescriptorRegistry`` shared with the running server."""
    return app.container.get(DescriptorRegistry)
