"""Unit tests for task dispatcher interfaces."""

from abc import ABC

import pytest

from spakky.task.interfaces.task_dispatcher import (
    IAsyncTaskDispatcher,
    ITaskDispatcher,
)


def test_task_dispatcher_is_abstract() -> None:
    """ITaskDispatcher가 ABC 서브클래스인지 검증한다."""
    assert issubclass(ITaskDispatcher, ABC)


def test_async_task_dispatcher_is_abstract() -> None:
    """IAsyncTaskDispatcher가 ABC 서브클래스인지 검증한다."""
    assert issubclass(IAsyncTaskDispatcher, ABC)


def test_task_dispatcher_cannot_be_instantiated() -> None:
    """ITaskDispatcher를 직접 인스턴스화할 수 없는지 검증한다."""
    with pytest.raises(TypeError):
        ITaskDispatcher()  # type: ignore[abstract] - ABC 인스턴스화 불가 테스트


def test_async_task_dispatcher_cannot_be_instantiated() -> None:
    """IAsyncTaskDispatcher를 직접 인스턴스화할 수 없는지 검증한다."""
    with pytest.raises(TypeError):
        IAsyncTaskDispatcher()  # type: ignore[abstract] - ABC 인스턴스화 불가 테스트


def test_task_dispatcher_has_dispatch_method() -> None:
    """ITaskDispatcher가 dispatch 추상 메서드를 가지는지 검증한다."""
    assert hasattr(ITaskDispatcher, "dispatch")
    assert getattr(ITaskDispatcher.dispatch, "__isabstractmethod__", False) is True


def test_async_task_dispatcher_has_dispatch_method() -> None:
    """IAsyncTaskDispatcher가 dispatch 추상 메서드를 가지는지 검증한다."""
    assert hasattr(IAsyncTaskDispatcher, "dispatch")
    assert getattr(IAsyncTaskDispatcher.dispatch, "__isabstractmethod__", False) is True
