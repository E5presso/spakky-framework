"""Unit tests for descriptor pool registry."""

from dataclasses import dataclass
from typing import Annotated

import pytest
from google.protobuf.descriptor import FileDescriptor, ServiceDescriptor
from google.protobuf.message import Message

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.error import DescriptorAlreadyRegisteredError
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry


@dataclass
class RegRequest:
    """Request message for registry tests."""

    name: Annotated[str, ProtoField(number=1)]


@dataclass
class RegResponse:
    """Response message for registry tests."""

    greeting: Annotated[str, ProtoField(number=1)]


class RegService:
    """Service class for registry tests."""

    @rpc()
    async def hello(self, request: RegRequest) -> RegResponse: ...


def _build_test_descriptor() -> tuple[DescriptorRegistry, str]:
    """Build and register a test file descriptor.

    Returns:
        Tuple of (registry, file_name).
    """
    fd = build_file_descriptor("reg.v1", "RegService", RegService)
    registry = DescriptorRegistry()
    registry.register(fd)
    return registry, fd.name


def test_register_returns_file_descriptor() -> None:
    """register should return a compiled FileDescriptor."""
    fd = build_file_descriptor("reg.v1", "RegService", RegService)
    registry = DescriptorRegistry()
    result = registry.register(fd)
    assert isinstance(result, FileDescriptor)
    assert result.name == fd.name


def test_is_registered_after_registration() -> None:
    """is_registered should return True after a file is registered."""
    registry, file_name = _build_test_descriptor()
    assert registry.is_registered(file_name) is True


def test_is_registered_for_unknown_file() -> None:
    """is_registered should return False for an unregistered file."""
    registry = DescriptorRegistry()
    assert registry.is_registered("unknown.proto") is False


def test_register_duplicate_expect_error() -> None:
    """register should raise DescriptorAlreadyRegisteredError on duplicate registration."""
    fd = build_file_descriptor("dup.v1", "RegService", RegService)
    registry = DescriptorRegistry()
    registry.register(fd)

    with pytest.raises(DescriptorAlreadyRegisteredError) as exc_info:
        registry.register(fd)

    assert exc_info.value.file_name == fd.name


def test_get_message_class_returns_message_subclass() -> None:
    """get_message_class should return a protobuf Message subclass."""
    registry, _ = _build_test_descriptor()
    msg_class = registry.get_message_class("reg.v1", "RegRequest")
    assert issubclass(msg_class, Message)


def test_get_message_class_creates_working_instance() -> None:
    """get_message_class should produce a class that can create serializable instances."""
    registry, _ = _build_test_descriptor()
    msg_class = registry.get_message_class("reg.v1", "RegRequest")
    instance = msg_class(name="test")
    serialized = instance.SerializeToString()
    assert isinstance(serialized, bytes)
    assert len(serialized) > 0


def test_get_message_class_caches_result() -> None:
    """get_message_class should return the same class on repeated calls."""
    registry, _ = _build_test_descriptor()
    first = registry.get_message_class("reg.v1", "RegRequest")
    second = registry.get_message_class("reg.v1", "RegRequest")
    assert first is second


def test_get_service_descriptor_returns_service_descriptor() -> None:
    """get_service_descriptor should return a ServiceDescriptor."""
    registry, _ = _build_test_descriptor()
    svc_desc = registry.get_service_descriptor("reg.v1", "RegService")
    assert isinstance(svc_desc, ServiceDescriptor)
    assert svc_desc.name == "RegService"


def test_get_service_descriptor_contains_methods() -> None:
    """get_service_descriptor should contain the registered method."""
    registry, _ = _build_test_descriptor()
    svc_desc = registry.get_service_descriptor("reg.v1", "RegService")
    assert "hello" in svc_desc.methods_by_name


def test_pool_property_returns_descriptor_pool() -> None:
    """pool property should expose the underlying DescriptorPool."""
    registry = DescriptorRegistry()
    assert registry.pool is not None
