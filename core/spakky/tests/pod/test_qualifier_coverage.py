"""Test pod edge cases for complete coverage."""

import pytest

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.qualifier import Qualifier
from spakky.core.pod.error import QualifierSelectorNotCallableError


def test_qualifier_with_selector() -> None:
    """Qualifier의 selector 함수가 올바르게 동작함을 검증한다."""

    @Pod()
    class TestPod:
        pass

    # Create a qualifier with a selector
    qualifier = Qualifier(selector=lambda pod: pod.name == "test_pod")

    # Get the pod
    pod = Pod.get(TestPod)

    # Test the selector
    assert qualifier.selector(pod) is True

    # Test with different name
    qualifier2 = Qualifier(selector=lambda pod: pod.name == "other_name")
    assert qualifier2.selector(pod) is False


def test_qualifier_with_invalid_selector() -> None:
    """Qualifier에 호출 불가능한 selector가 주어지면 QualifierSelectorNotCallableError가 발생함을 검증한다."""
    with pytest.raises(QualifierSelectorNotCallableError):
        Qualifier(selector="not_a_function")  # type: ignore

    # Test with other non-callable types
    with pytest.raises(QualifierSelectorNotCallableError):
        Qualifier(selector=123)  # type: ignore

    with pytest.raises(QualifierSelectorNotCallableError):
        Qualifier(selector=[])  # type: ignore
