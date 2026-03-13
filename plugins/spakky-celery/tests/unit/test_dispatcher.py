"""Tests for CeleryTaskDispatchAspect and AsyncCeleryTaskDispatchAspect."""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from spakky.task.stereotype.task_handler import TaskRoute

from spakky.plugins.celery.aspects.task_dispatch import (
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


def _create_mock_celery_app() -> MagicMock:
    """CeleryApp mock을 생성한다."""
    celery_app = MagicMock()
    celery_app.celery = MagicMock()
    celery_app.celery.send_task = MagicMock()
    celery_app.task_routes = {}
    return celery_app


def _create_joinpoint(
    name: str,
    celery_app: MagicMock,
    *,
    background: bool = False,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Any]:
    """task name과 TaskRoute 어노테이션이 설정된 joinpoint mock을 생성한다."""

    def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute(background=background)(joinpoint)

    task_name = _make_task_name(name)
    # background=False일 때 apply()가 호출되므로 mock task 등록
    if not background:
        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = return_value
        mock_task.apply.return_value = mock_result
        celery_app.task_routes[task_name] = mock_task

    return joinpoint


# ── Sync CeleryTaskDispatchAspect ──


def test_around_dispatches_task_via_send_task() -> None:
    """CeleryTaskDispatchAspect.around이 background=True일 때 send_task()를 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = CeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_joinpoint("send_email", celery_app, background=True)

    mock_async_result = MagicMock()
    mock_async_result.id = "task-abc-123"
    celery_app.celery.send_task.return_value = mock_async_result

    result = aspect.around(joinpoint, to="test@example.com", subject="Hi")

    celery_app.celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-abc-123"


def test_around_dispatches_task_with_positional_args() -> None:
    """CeleryTaskDispatchAspect.around이 positional args를 올바르게 전달하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = CeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_joinpoint("send_email", celery_app, background=True)

    aspect.around(joinpoint, "test@example.com", "Hi")

    celery_app.celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=("test@example.com", "Hi"),
        kwargs={},
    )


def test_around_background_false_calls_apply() -> None:
    """CeleryTaskDispatchAspect.around이 background=False일 때 apply()를 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = CeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_joinpoint("send_email", celery_app, background=False)

    aspect.around(joinpoint, to="test@example.com", subject="Hi")

    celery_app.task_routes[_make_task_name("send_email")].apply.assert_called_once_with(
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    celery_app.celery.send_task.assert_not_called()


def test_around_background_false_returns_result() -> None:
    """CeleryTaskDispatchAspect.around이 background=False일 때 apply() 결과를 반환하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = CeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_joinpoint(
        "send_email", celery_app, background=False, return_value="email_sent"
    )

    result = aspect.around(joinpoint, to="test@example.com")

    assert result == "email_sent"


def test_around_background_true_does_not_call_apply() -> None:
    """CeleryTaskDispatchAspect.around이 background=True일 때 apply()를 호출하지 않는지 검증한다."""
    celery_app = _create_mock_celery_app()
    # background=True일 때도 task_routes에 등록해서 apply가 호출되지 않음을 검증
    mock_task = MagicMock()
    celery_app.task_routes[_make_task_name("send_email")] = mock_task
    aspect = CeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_joinpoint("send_email", celery_app, background=True)

    aspect.around(joinpoint, to="test@example.com")

    mock_task.apply.assert_not_called()


def test_around_in_celery_task_context_calls_joinpoint() -> None:
    """CeleryTaskDispatchAspect.around이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = CeleryTaskDispatchAspect(celery_app)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.send_email"
    TaskRoute(background=False)(joinpoint)

    task_name = _make_task_name("send_email")
    mock_task = MagicMock()
    celery_app.task_routes[task_name] = mock_task

    # Simulate being inside a Celery task (current_task is not None)
    with patch(
        "spakky.plugins.celery.aspects.task_dispatch.current_task",
        new=MagicMock(),
    ):
        result = aspect.around(joinpoint, to="test@example.com")

    assert calls == [((), {"to": "test@example.com"})]
    celery_app.task_routes[_make_task_name("send_email")].apply.assert_not_called()
    assert result == "direct"


# ── Async AsyncCeleryTaskDispatchAspect ──


def _create_async_joinpoint(
    name: str,
    celery_app: MagicMock,
    *,
    background: bool = False,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Awaitable[Any]]:
    """task name과 TaskRoute 어노테이션이 설정된 async joinpoint mock을 생성한다."""

    async def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute(background=background)(joinpoint)

    task_name = _make_task_name(name)
    # background=False일 때 apply()가 호출되므로 mock task 등록
    if not background:
        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = return_value
        mock_task.apply.return_value = mock_result
        celery_app.task_routes[task_name] = mock_task

    return joinpoint


@pytest.mark.asyncio
async def test_async_around_dispatches_task_via_send_task() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 background=True일 때 send_task()를 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = AsyncCeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_async_joinpoint("async_send_email", celery_app, background=True)

    mock_async_result = MagicMock()
    mock_async_result.id = "task-async-456"
    celery_app.celery.send_task.return_value = mock_async_result

    result = await aspect.around_async(joinpoint, to="test@example.com", subject="Hi")

    celery_app.celery.send_task.assert_called_once_with(
        _make_task_name("async_send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-async-456"


@pytest.mark.asyncio
async def test_async_around_background_false_calls_apply() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 background=False일 때 apply()를 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = AsyncCeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_async_joinpoint(
        "async_send_email", celery_app, background=False
    )

    await aspect.around_async(joinpoint, to="test@example.com", subject="Hi")

    celery_app.task_routes[
        _make_task_name("async_send_email")
    ].apply.assert_called_once_with(
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
    )
    celery_app.celery.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_async_around_background_false_returns_result() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 background=False일 때 apply() 결과를 반환하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = AsyncCeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_async_joinpoint(
        "async_send_email", celery_app, background=False, return_value="email_sent"
    )

    result = await aspect.around_async(joinpoint, to="test@example.com")

    assert result == "email_sent"


@pytest.mark.asyncio
async def test_async_around_background_true_does_not_call_apply() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 background=True일 때 apply()를 호출하지 않는지 검증한다."""
    celery_app = _create_mock_celery_app()
    # background=True일 때도 task_routes에 등록해서 apply가 호출되지 않음을 검증
    mock_task = MagicMock()
    celery_app.task_routes[_make_task_name("async_send_email")] = mock_task
    aspect = AsyncCeleryTaskDispatchAspect(celery_app)
    joinpoint = _create_async_joinpoint("async_send_email", celery_app, background=True)

    await aspect.around_async(joinpoint, to="test@example.com")

    mock_task.apply.assert_not_called()


@pytest.mark.asyncio
async def test_async_around_in_celery_task_context_calls_joinpoint() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery_app = _create_mock_celery_app()
    aspect = AsyncCeleryTaskDispatchAspect(celery_app)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "async_send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.async_send_email"
    TaskRoute(background=False)(joinpoint)

    task_name = _make_task_name("async_send_email")
    mock_task = MagicMock()
    celery_app.task_routes[task_name] = mock_task

    # Simulate being inside a Celery task (current_task is not None)
    with patch(
        "spakky.plugins.celery.aspects.task_dispatch.current_task",
        new=MagicMock(),
    ):
        result = await aspect.around_async(joinpoint, to="test@example.com")

    assert calls == [((), {"to": "test@example.com"})]
    celery_app.task_routes[
        _make_task_name("async_send_email")
    ].apply.assert_not_called()
    assert result == "direct"
