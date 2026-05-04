from typing import Callable, overload

import pytest

from spakky.core.common.types import ObjectT
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.binding import PodBinding
from spakky.core.pod.interfaces.container import (
    CircularDependencyGraphDetectedError,
    IContainer,
    PodBindingNotSupportedError,
)


class DummyA:
    """테스트용 더미 클래스 A."""


class DummyB:
    """테스트용 더미 클래스 B."""


class LegacyContainerDouble(IContainer):
    """기존 커스텀 컨테이너 구현체와 같은 최소 test double."""

    @property
    def pods(self) -> dict[str, Pod]:
        return {}

    def add(self, obj: PodType) -> None:
        return

    @overload
    def get(self, type_: type[ObjectT]) -> ObjectT: ...

    @overload
    def get(self, type_: type[ObjectT], name: str) -> ObjectT: ...

    def get(self, type_: type[ObjectT], name: str | None = None) -> ObjectT | object:
        return object()

    @overload
    def get_or_none(self, type_: type[ObjectT]) -> ObjectT | None: ...

    @overload
    def get_or_none(self, type_: type[ObjectT], name: str) -> ObjectT | None: ...

    def get_or_none(
        self, type_: type[ObjectT], name: str | None = None
    ) -> ObjectT | None:
        return None

    @overload
    def contains(self, type_: type) -> bool: ...

    @overload
    def contains(self, type_: type, name: str) -> bool: ...

    def contains(self, type_: type, name: str | None = None) -> bool:
        return False

    def find(self, selector: Callable[[Pod], bool]) -> set[object]:
        return set()


def test_circular_dependency_error_empty_chain_expect_message_only() -> None:
    """빈 dependency_chain 시 기본 메시지만 반환함을 검증한다."""
    error = CircularDependencyGraphDetectedError(dependency_chain=[])
    assert str(error) == "Circular dependency graph detected"


def test_circular_dependency_error_with_chain_expect_formatted_path() -> None:
    """dependency_chain이 있을 때 시각적 경로를 포함한 메시지를 반환함을 검증한다."""
    error = CircularDependencyGraphDetectedError(
        dependency_chain=[DummyA, DummyB, DummyA]
    )
    result = str(error)
    assert "Circular dependency graph detected" in result
    assert "Dependency path:" in result
    assert "DummyA" in result
    assert "DummyB" in result
    assert "(CIRCULAR!)" in result


def test_circular_dependency_error_single_element_expect_circular_marker() -> None:
    """단일 요소 체인에서도 CIRCULAR 마커가 표시됨을 검증한다."""
    error = CircularDependencyGraphDetectedError(dependency_chain=[DummyA])
    result = str(error)
    assert "DummyA (CIRCULAR!)" in result


def test_container_binding_default_methods_expect_not_supported_error() -> None:
    """기존 IContainer 구현체가 binding 메서드 없이도 인스턴스화됨을 검증한다."""
    container = LegacyContainerDouble()

    with pytest.raises(PodBindingNotSupportedError):
        container.bind(PodBinding(interface=DummyA, implementation_type=DummyB))

    with pytest.raises(PodBindingNotSupportedError):
        container.bind_to_type(DummyA, DummyB)

    with pytest.raises(PodBindingNotSupportedError):
        container.bind_to_name(DummyA, "dummy_b")
