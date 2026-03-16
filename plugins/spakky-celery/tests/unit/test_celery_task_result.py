"""Tests for CeleryTaskResult."""

from unittest.mock import AsyncMock, MagicMock, patch

from spakky.task.interfaces.task_result import AbstractTaskResult

from spakky.plugins.celery.common.task_result import CeleryTaskResult


def test_celery_task_result_is_task_result() -> None:
    """CeleryTaskResult이 TaskResult의 구체 구현체임을 검증한다."""
    mock_async_result = MagicMock()
    mock_async_result.id = "abc-123"
    mock_async_result.get.return_value = "some-value"

    result: AbstractTaskResult[str] = CeleryTaskResult(mock_async_result)

    assert isinstance(result, AbstractTaskResult)


def test_celery_task_result_task_id_returns_async_result_id() -> None:
    """CeleryTaskResult.task_id가 AsyncResult.id를 반환하는지 검증한다."""
    mock_async_result = MagicMock()
    mock_async_result.id = "abc-123"

    result = CeleryTaskResult(mock_async_result)

    assert result.task_id == "abc-123"


def test_celery_task_result_get_delegates_to_async_result() -> None:
    """CeleryTaskResult.get()이 AsyncResult.get()의 결과를 반환하는지 검증한다."""
    mock_async_result = MagicMock()
    mock_async_result.get.return_value = "final-value"

    result: CeleryTaskResult[str] = CeleryTaskResult(mock_async_result)

    assert result.get() == "final-value"
    mock_async_result.get.assert_called_once_with()


async def test_celery_task_result_get_async_delegates_via_executor() -> None:
    """CeleryTaskResult.get_async()가 run_in_executor를 통해 AsyncResult.get()을 호출하는지 검증한다."""
    mock_async_result = MagicMock()
    mock_async_result.get.return_value = "async-final-value"

    result: CeleryTaskResult[str] = CeleryTaskResult(mock_async_result)

    with patch("spakky.plugins.celery.common.task_result.asyncio.get_running_loop") as mock_get_loop:
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value="async-final-value")
        mock_get_loop.return_value = mock_loop

        value = await result.get_async()

    assert value == "async-final-value"
    mock_loop.run_in_executor.assert_called_once_with(None, mock_async_result.get)
