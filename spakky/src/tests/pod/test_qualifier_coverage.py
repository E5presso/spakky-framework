"""Test pod edge cases for complete coverage."""

import pytest

from spakky.pod.annotations.pod import Pod
from spakky.pod.annotations.qualifier import Qualifier


def test_qualifier_with_selector() -> None:
    """Test Qualifier with selector function."""

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
    """Test Qualifier raises TypeError for non-callable selector."""
    with pytest.raises(TypeError) as exc_info:
        Qualifier(selector="not_a_function")  # type: ignore

    assert "Qualifier selector must be callable" in str(exc_info.value)
    assert "got str" in str(exc_info.value)

    # Test with other non-callable types
    with pytest.raises(TypeError):
        Qualifier(selector=123)  # type: ignore

    with pytest.raises(TypeError):
        Qualifier(selector=[])  # type: ignore
