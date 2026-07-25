"""Unit tests for gRPC plugin main.py initialize function."""

from pathlib import Path
from unittest.mock import MagicMock, call

import grpc
import pytest
from grpc_health.v1 import health
from spakky.core.application.application import SpakkyApplication
from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.main import (
    descriptor_registry,
    grpc_health_servicer,
    grpc_server_spec,
    initialize,
)
from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
)
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec

HEALTH_SERVICE_NAME = "grpc.health.v1.Health"
REFLECTION_SERVICE_NAME = "grpc.reflection.v1alpha.ServerReflection"


def _config(
    bind_addresses: tuple[str, ...] = (),
    server_options: dict[str, int | str] | None = None,
    tls_certificate_chain_file: Path | None = None,
    tls_private_key_file: Path | None = None,
    health_service_enabled: bool = False,
    reflection_service_enabled: bool = False,
) -> GrpcConfig:
    """Build a GrpcConfig directly, bypassing environment loading."""
    return GrpcConfig.model_construct(
        bind_addresses=bind_addresses,
        server_options=server_options if server_options is not None else {},
        tls_certificate_chain_file=tls_certificate_chain_file,
        tls_private_key_file=tls_private_key_file,
        tls_client_ca_file=None,
        require_client_auth=False,
        health_service_enabled=health_service_enabled,
        reflection_service_enabled=reflection_service_enabled,
    )


def test_initialize_registers_framework_integration_pods() -> None:
    """initialize() should register config, shared runtime pods, and processors."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_any_call(GrpcConfig)
    app.add.assert_any_call(descriptor_registry)
    app.add.assert_any_call(grpc_health_servicer)
    app.add.assert_any_call(grpc_server_spec)
    app.add.assert_any_call(RegisterServicesPostProcessor)
    app.add.assert_any_call(AddInterceptorsPostProcessor)
    app.add.assert_any_call(BindServerPostProcessor)
    assert app.add.call_count == 7


def test_initialize_registration_order() -> None:
    """PostProcessors should be registered in the expected order."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    expected_calls = [
        call(GrpcConfig),
        call(descriptor_registry),
        call(grpc_health_servicer),
        call(grpc_server_spec),
        call(RegisterServicesPostProcessor),
        call(AddInterceptorsPostProcessor),
        call(BindServerPostProcessor),
    ]
    app.add.assert_has_calls(expected_calls, any_order=False)


def test_descriptor_registry_factory_returns_registry() -> None:
    """descriptor_registry() should create the shared DescriptorRegistry."""
    assert isinstance(descriptor_registry(), DescriptorRegistry)


def test_grpc_health_servicer_factory_returns_async_servicer() -> None:
    """grpc_health_servicer() should create the asyncio health servicer."""
    assert isinstance(grpc_health_servicer(), health.aio.HealthServicer)


def test_grpc_server_spec_factory_uses_config_bind_addresses() -> None:
    """grpc_server_spec() should copy configured bind addresses into the spec."""
    config = _config(bind_addresses=("127.0.0.1:50051", "127.0.0.1:50052"))

    spec = grpc_server_spec(config, DescriptorRegistry(), health.aio.HealthServicer())

    assert isinstance(spec, GrpcServerSpec)
    assert spec.bind_addresses == ["127.0.0.1:50051", "127.0.0.1:50052"]


def test_grpc_server_spec_factory_without_tls_expect_plaintext_targets() -> None:
    """Without TLS material every bind address should stay a plaintext listener."""
    config = _config(bind_addresses=("127.0.0.1:50051",))

    spec = grpc_server_spec(config, DescriptorRegistry(), health.aio.HealthServicer())

    assert spec.bind_targets[0].credentials is None


def test_grpc_server_spec_factory_forwards_server_options() -> None:
    """grpc_server_spec() should pass configured channel arguments to the spec."""
    config = _config(server_options={"grpc.max_receive_message_length": 8_388_608})

    spec = grpc_server_spec(config, DescriptorRegistry(), health.aio.HealthServicer())

    assert spec.options == (("grpc.max_receive_message_length", 8_388_608),)


def test_grpc_server_spec_factory_with_tls_expect_secure_targets(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """Configured TLS material should turn every bind address into a secure port."""
    certificate_chain_file, private_key_file = tls_key_pair
    config = _config(
        bind_addresses=("127.0.0.1:50051",),
        tls_certificate_chain_file=certificate_chain_file,
        tls_private_key_file=private_key_file,
    )

    spec = grpc_server_spec(config, DescriptorRegistry(), health.aio.HealthServicer())

    assert isinstance(spec.bind_targets[0].credentials, grpc.ServerCredentials)


@pytest.mark.parametrize(
    ("health_enabled", "reflection_enabled", "expected_service_names"),
    [
        (True, True, {HEALTH_SERVICE_NAME, REFLECTION_SERVICE_NAME}),
        (True, False, {HEALTH_SERVICE_NAME}),
        (False, True, {REFLECTION_SERVICE_NAME}),
        (False, False, set()),
    ],
)
def test_grpc_server_spec_factory_registers_enabled_standard_services(
    health_enabled: bool,
    reflection_enabled: bool,
    expected_service_names: set[str],
) -> None:
    """Only the standard services enabled in configuration should be published."""
    config = _config(
        health_service_enabled=health_enabled,
        reflection_service_enabled=reflection_enabled,
    )
    registry = DescriptorRegistry()

    spec = grpc_server_spec(config, registry, health.aio.HealthServicer())

    assert set(registry.service_names) == expected_service_names
    assert len(spec.service_registrars) == len(expected_service_names)
