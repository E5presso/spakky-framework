"""Unit tests for direct in-process task execution."""

import pytest
from spakky.core.pod.annotations.pod import Pod

from spakky.task.direct import DirectTaskExecutor, DirectTaskInvocation
from spakky.task.error import (
    TaskApplicationContextNotFoundError,
    TaskAsyncInvocationRequiredError,
    TaskNotFoundError,
)
from spakky.task.stereotype.task_handler import TaskHandler, task


class _ApplicationContext:
    clear_count: int
    values: dict[str, object]

    def __init__(self, handler: object) -> None:
        self._handler = handler
        self.clear_count = 0
        self.values = {}

    def get(self, type_: type[object]) -> object:
        return self._handler

    def clear_context(self) -> None:
        self.clear_count += 1
        self.values.clear()

    def get_context_value(self, key: str) -> object | None:
        return self.values.get(key)

    def set_context_value(self, key: str, value: object) -> None:
        self.values[key] = value


def test_direct_executor_is_pod() -> None:
    """DirectTaskExecutor는 ApplicationContext에서 등록 가능한 Pod이다."""
    assert Pod.exists(DirectTaskExecutor)


def test_execute_invokes_task_in_existing_context_scope() -> None:
    """직접 실행은 기존 request-scope context를 clear하지 않고 task를 호출한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self, value: str) -> tuple[str, object | None]:
            return value.upper(), context.get_context_value("auth")

    context = _ApplicationContext(SampleTaskHandler())
    context.set_context_value("auth", "subject-1")
    executor = DirectTaskExecutor()
    executor.set_application_context(context)  # type: ignore[arg-type] - focused test double

    result = executor.execute(
        DirectTaskInvocation(
            handler_type=SampleTaskHandler,
            method_name="process",
            args=("ok",),
        )
    )

    assert result == ("OK", "subject-1")
    assert context.clear_count == 0


async def test_execute_async_invokes_async_task_in_existing_context_scope() -> None:
    """비동기 직접 실행도 기존 request-scope context를 유지한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        async def process(self) -> object | None:
            return context.get_context_value("auth")

    context = _ApplicationContext(SampleTaskHandler())
    context.set_context_value("auth", "subject-async")
    executor = DirectTaskExecutor()
    executor.set_application_context(context)  # type: ignore[arg-type] - focused test double

    result = await executor.execute_async(
        DirectTaskInvocation(
            handler_type=SampleTaskHandler,
            method_name="process",
        )
    )

    assert result == "subject-async"
    assert context.clear_count == 0


async def test_execute_async_accepts_sync_task() -> None:
    """비동기 호출자는 동기 task도 같은 context에서 실행할 수 있다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self) -> str:
            return "sync"

    context = _ApplicationContext(SampleTaskHandler())
    executor = DirectTaskExecutor()
    executor.set_application_context(context)  # type: ignore[arg-type] - focused test double

    result = await executor.execute_async(
        DirectTaskInvocation(
            handler_type=SampleTaskHandler,
            method_name="process",
        )
    )

    assert result == "sync"


def test_execute_rejects_async_task_on_sync_path() -> None:
    """동기 직접 실행 경로는 async task를 coroutine으로 누수하지 않는다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        async def process(self) -> str:
            return "async"

    context = _ApplicationContext(SampleTaskHandler())
    executor = DirectTaskExecutor()
    executor.set_application_context(context)  # type: ignore[arg-type] - focused test double

    with pytest.raises(TaskAsyncInvocationRequiredError):
        executor.execute(
            DirectTaskInvocation(
                handler_type=SampleTaskHandler,
                method_name="process",
            )
        )


def test_execute_raises_when_application_context_missing() -> None:
    """ApplicationContext가 없으면 직접 실행을 fail-fast 한다."""
    executor = DirectTaskExecutor()

    with pytest.raises(TaskApplicationContextNotFoundError):
        executor.execute(
            DirectTaskInvocation(handler_type=object, method_name="missing")
        )


def test_execute_raises_when_task_method_missing() -> None:
    """요청한 task method를 찾을 수 없으면 structured task error를 발생시킨다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self) -> None:
            return None

    context = _ApplicationContext(SampleTaskHandler())
    executor = DirectTaskExecutor()
    executor.set_application_context(context)  # type: ignore[arg-type] - focused test double

    with pytest.raises(TaskNotFoundError):
        executor.execute(
            DirectTaskInvocation(
                handler_type=SampleTaskHandler,
                method_name="missing",
            )
        )
