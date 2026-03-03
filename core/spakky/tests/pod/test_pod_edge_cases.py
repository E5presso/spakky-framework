"""Test pod edge cases for complete coverage."""

import pytest

from spakky.core.pod.annotations.pod import (
    Pod,
    UnexpectedDependencyNameInjectedError,
    UnexpectedDependencyTypeInjectedError,
)


def test_pod_instantiate_with_unexpected_dependency_name() -> None:
    """Pod 인스턴스화 시 예상치 못한 의존성 이름이 주어지면 예외가 발생함을 검증한다."""

    @Pod()
    class TestPod:
        def __init__(self, expected_dep: int) -> None:
            self.expected_dep = expected_dep

    pod = Pod.get(TestPod)

    # Try to instantiate with wrong dependency name
    with pytest.raises(UnexpectedDependencyNameInjectedError):
        pod.instantiate({"wrong_name": 42})


def test_pod_instantiate_with_wrong_dependency_type() -> None:
    """Pod 인스턴스화 시 필수 의존성에 None이 주어지면 예외가 발생함을 검증한다."""

    @Pod()
    class TestPod:
        def __init__(self, required_dep: int) -> None:
            self.required_dep = required_dep

    pod = Pod.get(TestPod)

    # Try to instantiate with None for required dependency
    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        pod.instantiate({"required_dep": None})


def test_pod_instantiate_with_none_and_default_value() -> None:
    """Pod 인스턴스화 시 None이 주어지면 기본값을 사용함을 검증한다."""

    @Pod()
    class TestPod:
        def __init__(self, dep: int = 10) -> None:
            self.dep = dep

    pod = Pod.get(TestPod)

    # Instantiate with None - should use default value
    instance = pod.instantiate({"dep": None})

    assert isinstance(instance, TestPod)
    assert instance.dep == 10  # Default value used
