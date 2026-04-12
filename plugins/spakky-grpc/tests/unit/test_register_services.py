"""Unit tests for RegisterServicesPostProcessor."""

from dataclasses import dataclass
from types import new_class
from unittest.mock import MagicMock

import pytest
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec

from tests.unit.conftest import GreeterController


@dataclass
class RegisterServicesHarness:
    """Bundle of processor + observable collaborators for behavior assertions."""

    processor: RegisterServicesPostProcessor
    container: MagicMock
    application_context: MagicMock
    registry: DescriptorRegistry
    spec: GrpcServerSpec


@pytest.fixture
def harness() -> RegisterServicesHarness:
    """Create a processor wired to a real registry/spec plus a mock container."""
    proc = RegisterServicesPostProcessor.__new__(RegisterServicesPostProcessor)

    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    registry = DescriptorRegistry()
    spec = GrpcServerSpec()

    def get_side_effect(type_: type, name: str | None = None) -> object:
        if type_ is DescriptorRegistry:
            return registry
        if type_ is GrpcServerSpec:
            return spec
        return MagicMock()

    container.get = MagicMock(side_effect=get_side_effect)

    proc.set_container(container)
    proc.set_application_context(application_context)
    return RegisterServicesHarness(
        processor=proc,
        container=container,
        application_context=application_context,
        registry=registry,
        spec=spec,
    )


def test_register_services_with_non_controller_pod_expect_pod_returned_untouched(
    harness: RegisterServicesHarness,
) -> None:
    """Non-controller Pods should pass through without affecting spec or registry."""
    plain_pod = object()

    result = harness.processor.post_process(plain_pod)

    assert result is plain_pod
    assert harness.spec.handlers == []
    assert harness.registry.is_registered("test/v1/GreeterController.proto") is False


def test_register_services_with_grpc_controller_expect_handler_appended_to_spec(
    harness: RegisterServicesHarness,
) -> None:
    """A @GrpcController Pod should append exactly one handler to the shared spec."""
    controller_instance = GreeterController()

    result = harness.processor.post_process(controller_instance)

    assert result is controller_instance
    assert len(harness.spec.handlers) == 1


def test_register_services_with_grpc_controller_expect_descriptor_registered(
    harness: RegisterServicesHarness,
) -> None:
    """Processing a controller should publish its file descriptor to the registry."""
    controller_instance = GreeterController()

    harness.processor.post_process(controller_instance)

    assert harness.registry.is_registered("test/v1/GreeterController.proto") is True


def test_register_services_with_same_controller_twice_expect_descriptor_registered_once(
    harness: RegisterServicesHarness,
) -> None:
    """Processing the same controller twice should not double-register the descriptor."""
    harness.processor.post_process(GreeterController())

    second_result = harness.processor.post_process(GreeterController())

    assert isinstance(second_result, GreeterController)
    assert harness.registry.is_registered("test/v1/GreeterController.proto") is True
    # Two handlers (one per Pod instance) but the descriptor is registered once.
    assert len(harness.spec.handlers) == 2


def test_register_services_with_aop_proxy_pod_expect_handler_appended_from_original_type(
    harness: RegisterServicesHarness,
) -> None:
    """AOP proxy Pods should be unwrapped so the original controller is registered."""
    proxy_class = new_class(
        GreeterController.__name__ + DYNAMIC_PROXY_CLASS_NAME_SUFFIX,
        bases=(GreeterController,),
    )
    proxy_instance = object.__new__(proxy_class)

    result = harness.processor.post_process(proxy_instance)

    assert result is proxy_instance
    assert len(harness.spec.handlers) == 1
    assert harness.registry.is_registered("test/v1/GreeterController.proto") is True


def test_unwrap_proxy_type_with_proxy_class_expect_original_base_returned() -> None:
    """_unwrap_proxy_type should strip the @DynamicProxy suffix to the original class."""
    proxy_class = new_class(
        GreeterController.__name__ + DYNAMIC_PROXY_CLASS_NAME_SUFFIX,
        bases=(GreeterController,),
    )

    result = RegisterServicesPostProcessor._unwrap_proxy_type(proxy_class)

    assert result is GreeterController


def test_unwrap_proxy_type_with_non_proxy_class_expect_same_class_returned() -> None:
    """_unwrap_proxy_type should return non-proxy types unchanged."""
    result = RegisterServicesPostProcessor._unwrap_proxy_type(GreeterController)

    assert result is GreeterController
