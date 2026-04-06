"""Unit tests for registry module."""

from dataclasses import dataclass
from typing import Annotated

import pytest
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.error import DescriptorAlreadyRegisteredError
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class PingRequest:
    """Test request message for registry tests."""

    payload: Annotated[str, ProtoField(number=1)]


@dataclass
class PingResponse:
    """Test response message for registry tests."""

    result: Annotated[str, ProtoField(number=1)]


@GrpcController(package="registry.test")
class PingService:
    """Test service for registry tests."""

    @rpc()
    async def ping(self, request: PingRequest) -> PingResponse:
        """Unary ping method."""
        ...


def test_register_adds_to_pool() -> None:
    """register가 descriptor_pool에 파일을 등록하는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    file_desc = registry.register(file_proto)
    assert file_desc.name == file_proto.name


def test_is_registered_returns_true_after_register() -> None:
    """등록 후 is_registered가 True를 반환하는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    registry.register(file_proto)
    assert registry.is_registered(file_proto.name)


def test_is_registered_returns_false_before_register() -> None:
    """등록 전 is_registered가 False를 반환하는지 검증한다."""
    registry = DescriptorRegistry()
    assert not registry.is_registered("nonexistent.proto")


def test_duplicate_registration_raises_error() -> None:
    """동일 파일 중복 등록 시 DescriptorAlreadyRegisteredError를 발생시키는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    registry.register(file_proto)
    with pytest.raises(DescriptorAlreadyRegisteredError) as exc_info:
        registry.register(file_proto)
    assert exc_info.value.file_name == file_proto.name


def test_find_message_descriptor() -> None:
    """등록된 메시지의 descriptor를 찾을 수 있는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    registry.register(file_proto)
    msg_desc = registry.find_message_descriptor("registry.test.PingRequest")
    assert msg_desc.name == "PingRequest"


def test_get_message_class() -> None:
    """등록된 메시지의 런타임 클래스를 생성할 수 있는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    registry.register(file_proto)
    msg_class = registry.get_message_class("registry.test.PingRequest")
    instance = msg_class(payload="hello")
    assert instance.payload == "hello"  # type: ignore[attr-defined] - dynamic protobuf message


def test_find_service_descriptor() -> None:
    """등록된 서비스의 descriptor를 찾을 수 있는지 검증한다."""
    registry = DescriptorRegistry()
    file_proto = build_file_descriptor(PingService)
    registry.register(file_proto)
    svc_desc = registry.find_service_descriptor("registry.test.PingService")
    assert svc_desc.name == "PingService"
    assert len(svc_desc.methods) == 1
    assert svc_desc.methods[0].name == "ping"


def test_registry_with_custom_pool() -> None:
    """커스텀 DescriptorPool을 주입할 수 있는지 검증한다."""
    from google.protobuf.descriptor_pool import DescriptorPool

    pool = DescriptorPool()
    registry = DescriptorRegistry(pool=pool)
    assert registry.pool is pool
