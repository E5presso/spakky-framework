"""Unit tests for gRPC plugin main.py initialize function."""

from unittest.mock import MagicMock, call

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.main import (
    descriptor_registry,
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


def test_initialize_registers_framework_integration_pods() -> None:
    """initialize() should register config, shared runtime pods, and processors."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_any_call(GrpcConfig)
    app.add.assert_any_call(descriptor_registry)
    app.add.assert_any_call(grpc_server_spec)
    app.add.assert_any_call(RegisterServicesPostProcessor)
    app.add.assert_any_call(AddInterceptorsPostProcessor)
    app.add.assert_any_call(BindServerPostProcessor)
    assert app.add.call_count == 6


def test_initialize_registration_order() -> None:
    """PostProcessors should be registered in the expected order."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    expected_calls = [
        call(GrpcConfig),
        call(descriptor_registry),
        call(grpc_server_spec),
        call(RegisterServicesPostProcessor),
        call(AddInterceptorsPostProcessor),
        call(BindServerPostProcessor),
    ]
    app.add.assert_has_calls(expected_calls, any_order=False)


def test_descriptor_registry_factory_returns_registry() -> None:
    """descriptor_registry() should create the shared DescriptorRegistry."""
    assert isinstance(descriptor_registry(), DescriptorRegistry)


def test_grpc_server_spec_factory_uses_config_bind_addresses() -> None:
    """grpc_server_spec() should copy configured bind addresses into the spec."""
    config = GrpcConfig.model_construct(
        bind_addresses=("127.0.0.1:50051", "127.0.0.1:50052")
    )

    spec = grpc_server_spec(config)

    assert isinstance(spec, GrpcServerSpec)
    assert spec.bind_addresses == ["127.0.0.1:50051", "127.0.0.1:50052"]
