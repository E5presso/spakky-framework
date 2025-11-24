"""Test pod decorator edge cases for complete coverage."""

import pytest

from spakky.pod.annotations.pod import (
    CannotDeterminePodTypeError,
    CannotUsePositionalOnlyArgsInPodError,
    CannotUseVarArgsInPodError,
    Pod,
)


def test_pod_cannot_use_positional_only_args() -> None:
    """Test that @Pod raises error with positional-only arguments."""
    with pytest.raises(CannotUsePositionalOnlyArgsInPodError):

        @Pod()
        def bad_pod(x, /) -> int:  # Positional-only argument
            return x


def test_pod_cannot_use_var_positional_args() -> None:
    """Test that @Pod raises error with *args."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        class BadPod:
            def __init__(self, *args: int) -> None:
                pass


def test_pod_cannot_use_var_keyword_args() -> None:
    """Test that @Pod raises error with **kwargs."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        class BadPod:
            def __init__(self, **kwargs: int) -> None:
                pass


def test_pod_cannot_determine_type_without_annotation() -> None:
    """Test that @Pod raises error when parameter has no type annotation."""
    with pytest.raises(CannotDeterminePodTypeError):

        @Pod()
        class BadPod:
            def __init__(self, x) -> None:  # No type annotation
                pass
