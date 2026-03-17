"""Celery-backed implementation of TaskResult."""

import asyncio
from typing import Generic, TypeVar, cast

from spakky.task.interfaces.task_result import AbstractTaskResult

from celery.result import AsyncResult

T = TypeVar("T")


class CeleryTaskResult(AbstractTaskResult[T], Generic[T]):
    """Wraps a Celery AsyncResult, exposing the broker-agnostic TaskResult interface."""

    _result: AsyncResult

    def __init__(self, result: AsyncResult) -> None:
        """Wrap a Celery AsyncResult."""
        self._result = result

    @property
    def task_id(self) -> str:
        return self._result.id

    def get(self) -> T:
        return cast(T, self._result.get())

    async def get_async(self) -> T:
        loop = asyncio.get_running_loop()
        return cast(T, await loop.run_in_executor(None, self._result.get))
