"""Unit tests for the deferred server configuration collected in GrpcServerSpec."""

from unittest.mock import MagicMock

import grpc
import grpc.aio
import pytest
from spakky.plugins.grpc.server_spec import GrpcServerSpec


def test_bind_addresses_expect_registration_order() -> None:
    """bind_addresses should report every registered address in order."""
    spec = GrpcServerSpec()

    spec.add_insecure_port("127.0.0.1:50051")
    spec.add_secure_port("127.0.0.1:50052", MagicMock(spec=grpc.ServerCredentials))

    assert spec.bind_addresses == ["127.0.0.1:50051", "127.0.0.1:50052"]


def test_add_secure_port_expect_credentials_attached_to_target() -> None:
    """A secure bind target should carry the credentials protecting its address."""
    credentials = MagicMock(spec=grpc.ServerCredentials)
    spec = GrpcServerSpec()

    spec.add_secure_port("127.0.0.1:50052", credentials)

    assert spec.bind_targets[0].credentials is credentials


def test_options_from_mapping_expect_channel_argument_pairs() -> None:
    """Channel arguments should be stored as the pair sequence gRPC expects."""
    spec = GrpcServerSpec(options={"grpc.max_connection_age_ms": 60_000})

    assert spec.options == (("grpc.max_connection_age_ms", 60_000),)


def test_options_omitted_expect_grpc_defaults_kept() -> None:
    """Omitting options should leave the gRPC defaults untouched."""
    assert GrpcServerSpec().options == ()


@pytest.mark.asyncio
async def test_build_async_expect_options_forwarded_to_grpc_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Channel arguments must reach grpc.aio.server, not merely sit on the spec."""
    created_with: dict[str, object] = {}

    def _record_server(**kwargs: object) -> MagicMock:
        created_with.update(kwargs)
        return MagicMock(spec=grpc.aio.Server)

    monkeypatch.setattr(grpc.aio, "server", _record_server)
    spec = GrpcServerSpec(options={"grpc.max_receive_message_length": 8_388_608})

    await spec.build_async()

    assert created_with["options"] == (("grpc.max_receive_message_length", 8_388_608),)


@pytest.mark.asyncio
async def test_build_async_with_insecure_target_expect_os_assigned_port() -> None:
    """Building a spec bound to port 0 should report the kernel-assigned port."""
    spec = GrpcServerSpec()
    spec.add_insecure_port("127.0.0.1:0")

    server = await spec.build_async()
    try:
        assert spec.bound_ports[0] > 0
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_build_async_invokes_registered_service_registrars() -> None:
    """Standard-service registrars should run against the instantiated server."""
    spec = GrpcServerSpec()
    registered: list[grpc.aio.Server] = []

    async def _register(server: grpc.aio.Server) -> None:
        registered.append(server)

    spec.add_service_registrar(_register)

    server = await spec.build_async()
    try:
        assert registered == [server]
    finally:
        await server.stop(grace=None)
