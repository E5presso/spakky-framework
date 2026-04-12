"""Unit tests for RegisterServicesPostProcessor."""

from types import new_class
from unittest.mock import MagicMock

import grpc.aio
import pytest
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)
from spakky.plugins.grpc.schema.registry import DescriptorRegistry

from tests.unit.conftest import GreeterController


@pytest.fixture
def processor() -> RegisterServicesPostProcessor:
    """Create a configured RegisterServicesPostProcessor."""
    proc = RegisterServicesPostProcessor.__new__(RegisterServicesPostProcessor)

    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    registry = DescriptorRegistry()
    server = MagicMock(spec=grpc.aio.Server)
    server.add_generic_rpc_handlers = MagicMock()

    def get_side_effect(type_: type, name: str | None = None) -> object:
        if type_ is DescriptorRegistry:
            return registry
        if type_ is grpc.aio.Server:
            return server
        return MagicMock()

    container.get = MagicMock(side_effect=get_side_effect)

    proc.set_container(container)
    proc.set_application_context(application_context)
    return proc


def test_register_services_skips_non_controller(
    processor: RegisterServicesPostProcessor,
) -> None:
    """Non-controller Pods should be returned unchanged."""
    plain_pod = object()
    result = processor.post_process(plain_pod)
    assert result is plain_pod


def test_register_services_processes_grpc_controller(
    processor: RegisterServicesPostProcessor,
) -> None:
    """@GrpcController Pod should trigger service registration."""
    controller_instance = GreeterController()
    result = processor.post_process(controller_instance)

    assert result is controller_instance
    container = (
        processor._RegisterServicesPostProcessor__container  # pyrefly: ignore - name-mangled private attr access
    )
    server = container.get(grpc.aio.Server)
    server.add_generic_rpc_handlers.assert_called_once()


def test_register_services_registers_descriptor_in_registry(
    processor: RegisterServicesPostProcessor,
) -> None:
    """Processing a controller should register its descriptor."""
    controller_instance = GreeterController()
    processor.post_process(controller_instance)

    container = (
        processor._RegisterServicesPostProcessor__container  # pyrefly: ignore - name-mangled private attr access
    )
    registry: DescriptorRegistry = container.get(DescriptorRegistry)
    assert registry.is_registered("test/v1/GreeterController.proto")


def test_register_services_skips_already_registered_descriptor(
    processor: RegisterServicesPostProcessor,
) -> None:
    """Processing the same controller twice should not raise."""
    controller_instance = GreeterController()
    processor.post_process(controller_instance)

    controller_instance_2 = GreeterController()
    result = processor.post_process(controller_instance_2)
    assert result is controller_instance_2


def test_register_services_unwraps_aop_proxy_type(
    processor: RegisterServicesPostProcessor,
) -> None:
    """AOP proxy Pod should be unwrapped to the original controller type."""
    proxy_class = new_class(
        GreeterController.__name__ + DYNAMIC_PROXY_CLASS_NAME_SUFFIX,
        bases=(GreeterController,),
    )
    proxy_instance = object.__new__(proxy_class)

    result = processor.post_process(proxy_instance)
    assert result is proxy_instance

    container = (
        processor._RegisterServicesPostProcessor__container  # pyrefly: ignore - name-mangled private attr access
    )
    server = container.get(grpc.aio.Server)
    server.add_generic_rpc_handlers.assert_called_once()


def test_unwrap_proxy_type_returns_original_class() -> None:
    """_unwrap_proxy_type should strip the @DynamicProxy suffix."""
    proxy_class = new_class(
        GreeterController.__name__ + DYNAMIC_PROXY_CLASS_NAME_SUFFIX,
        bases=(GreeterController,),
    )
    result = RegisterServicesPostProcessor._unwrap_proxy_type(proxy_class)
    assert result is GreeterController


def test_unwrap_proxy_type_returns_non_proxy_unchanged() -> None:
    """_unwrap_proxy_type should return non-proxy types unchanged."""
    result = RegisterServicesPostProcessor._unwrap_proxy_type(GreeterController)
    assert result is GreeterController
