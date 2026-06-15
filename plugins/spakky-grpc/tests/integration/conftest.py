"""Integration-test fixtures booting a real ``grpc.aio.Server`` per test."""

from collections.abc import AsyncIterator, Iterator
from os import environ

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import spakky.plugins.grpc
import spakky.tracing
from spakky.plugins.grpc.config import SPAKKY_GRPC_CONFIG_ENV_PREFIX
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from tests.integration import apps


def _build_app(*, with_tracing: bool) -> SpakkyApplication:
    """Build and start a SpakkyApplication bound to an OS-assigned port.

    The spec requests ``127.0.0.1:0`` so the kernel picks a free port at
    ``build()`` time, avoiding the race window between reserving a port
    and the server binding it.
    """
    plugins = {spakky.plugins.grpc.PLUGIN_NAME}
    if with_tracing:
        plugins.add(spakky.tracing.PLUGIN_NAME)

    bind_addresses_env = f"{SPAKKY_GRPC_CONFIG_ENV_PREFIX}BIND_ADDRESSES"
    previous_bind_addresses = environ.get(bind_addresses_env)
    environ[bind_addresses_env] = '["127.0.0.1:0"]'
    try:
        app = (
            SpakkyApplication(ApplicationContext())
            .load_plugins(include=plugins)
            .scan(apps)
        )
        app.start()
        return app
    finally:
        if previous_bind_addresses is None:
            environ.pop(bind_addresses_env, None)
        else:
            environ[bind_addresses_env] = previous_bind_addresses


def _port_of(app: SpakkyApplication) -> int:
    """Return the OS-assigned port the server is listening on."""
    return app.container.get(GrpcServerSpec).bound_ports[0]


@pytest.fixture(name="app")
def get_app_fixture() -> Iterator[SpakkyApplication]:
    """Boot a SpakkyApplication with tracing enabled and tear it down afterwards."""
    app = _build_app(with_tracing=True)
    try:
        yield app
    finally:
        app.stop()


@pytest.fixture(name="app_without_tracing")
def get_app_without_tracing_fixture() -> Iterator[SpakkyApplication]:
    """Boot a SpakkyApplication with only the gRPC plugin (no tracing)."""
    app = _build_app(with_tracing=False)
    try:
        yield app
    finally:
        app.stop()


@pytest.fixture(name="port")
def get_port_fixture(app: SpakkyApplication) -> int:
    """Return the OS-assigned port the running server is listening on."""
    return _port_of(app)


@pytest_asyncio.fixture(name="channel")
async def get_channel_fixture(
    app: SpakkyApplication,
) -> AsyncIterator[grpc.aio.Channel]:
    """Open an insecure channel against the running test server."""
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{_port_of(app)}")
    try:
        yield channel
    finally:
        await channel.close()


@pytest.fixture(name="registry")
def get_registry_fixture(app: SpakkyApplication) -> DescriptorRegistry:
    """Expose the ``DescriptorRegistry`` shared with the running server."""
    return app.container.get(DescriptorRegistry)
