"""Celery-backed implementation of TaskResult."""

from typing import Generic, TypeVar, cast

from spakky.task.interfaces.task_result import AbstractTaskResult

from celery.result import AsyncResult

T = TypeVar("T")


class CeleryTaskResult(AbstractTaskResult[T], Generic[T]):
    """Wraps a Celery AsyncResult, exposing the broker-agnostic TaskResult interface."""

    _result: AsyncResult

    def __init__(self, result: AsyncResult) -> None:
        self._result = result

    @property
    def task_id(self) -> str:
        return self._result.id

    def get(self) -> T:
        return cast(T, self._result.get())
