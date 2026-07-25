"""Unit tests for publishing the standard health and reflection services."""

from unittest.mock import MagicMock

import grpc.aio
import pytest
from grpc_health.v1 import health, health_pb2
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from spakky.plugins.grpc.standard_services import (
    enable_health_service,
    enable_reflection_service,
)

from tests.unit.conftest import GreeterController

HEALTH_FILE_NAME = "grpc_health/v1/health.proto"
HEALTH_SERVICE_NAME = "grpc.health.v1.Health"
REFLECTION_SERVICE_NAME = "grpc.reflection.v1alpha.ServerReflection"
GREETER_SERVICE_NAME = "test.v1.GreeterController"


def test_enable_health_service_mirrors_health_schema_into_registry() -> None:
    """The health schema must be describable through the plugin's own pool."""
    registry = DescriptorRegistry()

    enable_health_service(GrpcServerSpec(), registry, health.aio.HealthServicer())

    assert registry.is_registered(HEALTH_FILE_NAME)
    assert HEALTH_SERVICE_NAME in registry.service_names


def test_enable_health_service_twice_expect_single_registration() -> None:
    """Re-enabling health on a shared registry must not re-register its schema."""
    registry = DescriptorRegistry()
    servicer = health.aio.HealthServicer()

    enable_health_service(GrpcServerSpec(), registry, servicer)
    enable_health_service(GrpcServerSpec(), registry, servicer)

    assert registry.service_names.count(HEALTH_SERVICE_NAME) == 1


@pytest.mark.asyncio
async def test_enable_health_service_registers_servicer_on_built_server() -> None:
    """The registrar should attach the health servicer to the concrete server."""
    spec = GrpcServerSpec()
    server = MagicMock(spec=grpc.aio.Server)

    enable_health_service(spec, DescriptorRegistry(), health.aio.HealthServicer())
    await spec.service_registrars[0](server)

    registered_service_names = {
        call.args[0] for call in server.add_registered_method_handlers.call_args_list
    }
    assert HEALTH_SERVICE_NAME in registered_service_names


@pytest.mark.asyncio
async def test_enable_health_service_seeds_registered_services_as_serving() -> None:
    """A probe naming a registered service must answer SERVING, not NOT_FOUND."""
    spec = GrpcServerSpec()
    registry = DescriptorRegistry()
    registry.register(build_file_descriptor(GreeterController))
    servicer = health.aio.HealthServicer()

    enable_health_service(spec, registry, servicer)
    await spec.service_registrars[0](MagicMock(spec=grpc.aio.Server))

    checked = await servicer.Check(
        health_pb2.HealthCheckRequest(service=GREETER_SERVICE_NAME),
        MagicMock(spec=grpc.aio.ServicerContext),
    )
    assert checked.status == health_pb2.HealthCheckResponse.SERVING


@pytest.mark.asyncio
async def test_enable_reflection_service_advertises_registry_service_names() -> None:
    """Reflection should advertise every service the registry knows at build time."""
    spec = GrpcServerSpec()
    registry = DescriptorRegistry()
    server = MagicMock(spec=grpc.aio.Server)

    enable_reflection_service(spec, registry)
    await spec.service_registrars[0](server)

    registered_service_names = {
        call.args[0] for call in server.add_registered_method_handlers.call_args_list
    }
    assert REFLECTION_SERVICE_NAME in registry.service_names
    assert REFLECTION_SERVICE_NAME in registered_service_names
