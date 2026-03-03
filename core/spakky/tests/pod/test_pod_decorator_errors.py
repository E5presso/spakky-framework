"""Test pod decorator edge cases for complete coverage."""

import pytest

from spakky.core.pod.annotations.pod import (
    CannotDeterminePodTypeError,
    CannotUsePositionalOnlyArgsInPodError,
    CannotUseVarArgsInPodError,
    Pod,
)


def test_pod_cannot_use_positional_only_args() -> None:
    """@Pod가 위치 전용 인자(positional-only)를 사용할 때 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotUsePositionalOnlyArgsInPodError):

        @Pod()
        def bad_pod(x, /) -> int:  # Positional-only argument  # type: ignore
            return x


def test_pod_cannot_use_var_positional_args() -> None:
    """@Pod가 *args를 사용할 때 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        class BadPod:
            def __init__(self, *args: int) -> None:
                pass


def test_pod_cannot_use_var_keyword_args() -> None:
    """@Pod가 **kwargs를 사용할 때 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        class BadPod:
            def __init__(self, **kwargs: int) -> None:
                pass


def test_pod_cannot_determine_type_without_annotation() -> None:
    """@Pod가 타입 어노테이션이 없는 파라미터가 있을 때 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotDeterminePodTypeError):

        @Pod()
        class BadPod:
            def __init__(self, x) -> None:  # No type annotation  # type: ignore
                pass
