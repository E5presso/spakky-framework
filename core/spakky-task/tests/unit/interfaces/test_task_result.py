"""Tests for TaskResult abstract interface."""

import pytest
from spakky.core.common.interfaces.equatable import IEquatable

from spakky.task.interfaces.task_result import AbstractTaskResult


def test_task_result_cannot_be_instantiated() -> None:
    """TaskResult은 직접 인스턴스화할 수 없다."""
    with pytest.raises(TypeError):
        AbstractTaskResult()  # type: ignore[abstract] - intentional instantiation test


def test_task_result_concrete_subclass_works() -> None:
    """TaskResult 구체 구현체가 task_id와 get()을 올바르게 노출하는지 검증한다."""

    class ConcreteResult(AbstractTaskResult[str]):
        @property
        def task_id(self) -> IEquatable:
            return "test-id"

        def get(self) -> str:
            return "result-value"

        async def get_async(self) -> str:
            return "result-value"

    result = ConcreteResult()
    assert result.task_id == "test-id"
    assert result.get() == "result-value"


async def test_task_result_get_async_works() -> None:
    """TaskResult 구체 구현체의 get_async()가 올바르게 동작하는지 검증한다."""

    class ConcreteResult(AbstractTaskResult[str]):
        @property
        def task_id(self) -> IEquatable:
            return "test-id"

        def get(self) -> str:
            return "result-value"

        async def get_async(self) -> str:
            return "async-result-value"

    result = ConcreteResult()
    assert await result.get_async() == "async-result-value"
