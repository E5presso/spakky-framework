"""Test pod edge cases for complete coverage."""

import pytest

from spakky.pod.annotations.pod import (
    Pod,
    UnexpectedDependencyNameInjectedError,
    UnexpectedDependencyTypeInjectedError,
)


def test_pod_instantiate_with_unexpected_dependency_name() -> None:
    """Test pod instantiation with unexpected dependency name."""

    @Pod()
    class TestPod:
        def __init__(self, expected_dep: int) -> None:
            self.expected_dep = expected_dep

    pod = Pod.get(TestPod)

    # Try to instantiate with wrong dependency name
    with pytest.raises(UnexpectedDependencyNameInjectedError):
        pod.instantiate({"wrong_name": 42})


def test_pod_instantiate_with_wrong_dependency_type() -> None:
    """Test pod instantiation with wrong dependency type (None when not optional)."""

    @Pod()
    class TestPod:
        def __init__(self, required_dep: int) -> None:
            self.required_dep = required_dep

    pod = Pod.get(TestPod)

    # Try to instantiate with None for required dependency
    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        pod.instantiate({"required_dep": None})


def test_pod_instantiate_with_none_and_default_value() -> None:
    """Test pod instantiation where None is provided but default exists."""

    @Pod()
    class TestPod:
        def __init__(self, dep: int = 10) -> None:
            self.dep = dep

    pod = Pod.get(TestPod)

    # Instantiate with None - should use default value
    instance = pod.instantiate({"dep": None})

    assert isinstance(instance, TestPod)
    assert instance.dep == 10  # Default value used
