"""Tests for CeleryTaskDispatchAspect and AsyncCeleryTaskDispatchAspect."""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from spakky.task.stereotype.task_handler import TaskRoute

from spakky.plugins.celery.aspects.task_dispatch import (
    CELERY_TASK_CONTEXT_KEY,
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.task_result import CeleryTaskResult

# Test constants for task naming
TEST_MODULE = "test_module"
TEST_HANDLER_CLASS = "TestHandler"


def _make_task_name(method_name: str) -> str:
    """Creates fully qualified task name for test assertions."""
    return f"{TEST_MODULE}.{TEST_HANDLER_CLASS}.{method_name}"


# ── Fixtures ──


def _create_mock_celery() -> MagicMock:
    """Celery mock을 생성한다."""
    celery = MagicMock()
    celery.send_task = MagicMock()
    return celery


def _create_mock_application_context(*, inside_task: bool = False) -> MagicMock:
    """IApplicationContext mock을 생성한다."""
    context = MagicMock()
    context.get_context_value.return_value = True if inside_task else None
    return context


def _create_joinpoint(
    name: str,
    *,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Any]:
    """task name과 TaskRoute 어노테이션이 설정된 joinpoint mock을 생성한다."""

    def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute()(joinpoint)
    return joinpoint


# ── Sync CeleryTaskDispatchAspect ──


def test_around_dispatches_task_via_send_task() -> None:
    """CeleryTaskDispatchAspect.around이 send_task()를 호출하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_joinpoint("send_email")

    mock_async_result = MagicMock()
    mock_async_result.id = "task-abc-123"
    celery.send_task.return_value = mock_async_result

    result = aspect.around(joinpoint, to="test@example.com", subject="Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-abc-123"


def test_around_dispatches_task_with_positional_args() -> None:
    """CeleryTaskDispatchAspect.around이 positional args를 올바르게 전달하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_joinpoint("send_email")

    aspect.around(joinpoint, "test@example.com", "Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=("test@example.com", "Hi"),
        kwargs={},
    )


def test_around_in_celery_task_context_calls_joinpoint() -> None:
    """CeleryTaskDispatchAspect.around이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery = _create_mock_celery()
    app_context = _create_mock_application_context(inside_task=True)
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(app_context)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.send_email"
    TaskRoute()(joinpoint)

    result = aspect.around(joinpoint, to="test@example.com")

    app_context.get_context_value.assert_called_once_with(CELERY_TASK_CONTEXT_KEY)
    assert calls == [((), {"to": "test@example.com"})]
    celery.send_task.assert_not_called()
    assert result == "direct"


# ── Async AsyncCeleryTaskDispatchAspect ──


def _create_async_joinpoint(
    name: str,
    *,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Awaitable[Any]]:
    """task name과 TaskRoute 어노테이션이 설정된 async joinpoint mock을 생성한다."""

    async def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute()(joinpoint)
    return joinpoint


@pytest.mark.asyncio
async def test_async_around_dispatches_task_via_send_task() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 send_task()를 호출하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_async_joinpoint("async_send_email")

    mock_async_result = MagicMock()
    mock_async_result.id = "task-async-456"
    celery.send_task.return_value = mock_async_result

    result = await aspect.around_async(joinpoint, to="test@example.com", subject="Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("async_send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-async-456"


@pytest.mark.asyncio
async def test_async_around_in_celery_task_context_calls_joinpoint() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery = _create_mock_celery()
    app_context = _create_mock_application_context(inside_task=True)
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(app_context)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "async_send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.async_send_email"
    TaskRoute()(joinpoint)

    result = await aspect.around_async(joinpoint, to="test@example.com")

    app_context.get_context_value.assert_called_once_with(CELERY_TASK_CONTEXT_KEY)
    assert calls == [((), {"to": "test@example.com"})]
    celery.send_task.assert_not_called()
    assert result == "direct"
