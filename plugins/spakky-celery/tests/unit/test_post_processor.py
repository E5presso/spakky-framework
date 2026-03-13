"""Tests for CeleryPostProcessor."""

import os
from unittest.mock import MagicMock

from spakky.task.stereotype.task_handler import TaskHandler, task

from spakky.plugins.celery.app import CeleryApp
from spakky.plugins.celery.common.config import CeleryConfig
from spakky.plugins.celery.post_processor import CeleryPostProcessor


@TaskHandler()
class _SampleTaskHandler:
    @task
    def send_email(self, to: str, subject: str) -> None:
        pass

    @task
    def process_data(self, data: str) -> None:
        pass


def _create_config(
    *, broker_url: str = "amqp://test:test@localhost:5672//"
) -> CeleryConfig:
    """테스트용 CeleryConfig를 생성한다."""
    os.environ["SPAKKY_CELERY__BROKER_URL"] = broker_url
    try:
        return CeleryConfig()
    finally:
        del os.environ["SPAKKY_CELERY__BROKER_URL"]


def _create_celery_app(config: CeleryConfig | None = None) -> CeleryApp:
    """테스트용 CeleryApp을 생성한다."""
    if config is None:
        config = _create_config()
    return CeleryApp(config)


def _create_post_processor(celery_app: CeleryApp) -> CeleryPostProcessor:
    """CeleryPostProcessor를 생성하고 Aware 인터페이스를 설정한다."""
    container_mock = MagicMock()
    container_mock.get.return_value = celery_app

    context_mock = MagicMock()

    post_processor = CeleryPostProcessor()
    post_processor.set_container(container_mock)
    post_processor.set_application_context(context_mock)
    return post_processor


def test_celery_post_processor_registers_tasks_on_post_process() -> None:
    """CeleryPostProcessor가 post_process()에서 @task 메서드를 Celery 태스크로 등록하는지 검증한다."""
    celery_app = _create_celery_app()
    post_processor = _create_post_processor(celery_app)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    registered_tasks = list(celery_app.celery.tasks.keys())
    # Use specific prefix to avoid matching tasks from other test modules
    sample_handler_prefix = "tests.unit.test_post_processor._SampleTaskHandler"
    send_email_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.send_email"
    ]
    process_data_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.process_data"
    ]

    assert len(send_email_tasks) == 1
    assert len(process_data_tasks) == 1


def test_celery_post_processor_collects_task_routes() -> None:
    """CeleryPostProcessor가 post_process()에서 task route를 수집하는지 검증한다."""
    celery_app = _create_celery_app()
    post_processor = _create_post_processor(celery_app)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    assert len(celery_app.task_routes) == 2


def test_celery_post_processor_ignores_non_task_handler_pods() -> None:
    """CeleryPostProcessor가 @TaskHandler가 아닌 Pod를 무시하는지 검증한다."""
    celery_app = _create_celery_app()
    post_processor = _create_post_processor(celery_app)

    class NotATaskHandler:
        def some_method(self) -> None:
            pass

    result = post_processor.post_process(NotATaskHandler())

    assert isinstance(result, NotATaskHandler)
    assert len(celery_app.task_routes) == 0


def test_celery_post_processor_returns_pod() -> None:
    """CeleryPostProcessor.post_process()가 pod를 반환하는지 검증한다."""
    celery_app = _create_celery_app()
    post_processor = _create_post_processor(celery_app)
    handler = _SampleTaskHandler()

    result = post_processor.post_process(handler)

    assert result is handler


def test_celery_post_processor_registers_wrapper_with_context_isolation() -> None:
    """등록된 래퍼가 실행 시 컨텍스트를 비우고 컨테이너에서 핸들러를 다시 조회하는지 검증한다."""

    @TaskHandler()
    class TrackingTaskHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        def track(self, value: str) -> str:
            self.calls.append(value)
            return value

    celery_app_mock = MagicMock()
    application_context_mock = MagicMock()
    tracking_handler = TrackingTaskHandler()

    container_mock = MagicMock()

    def get_from_container(type_: object) -> object:
        if type_ is CeleryApp:
            return celery_app_mock
        if type_ is TrackingTaskHandler:
            return tracking_handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    container_mock.get.side_effect = get_from_container

    post_processor = CeleryPostProcessor()
    post_processor.set_container(container_mock)
    post_processor.set_application_context(application_context_mock)

    post_processor.post_process(tracking_handler)

    register_calls = celery_app_mock.register_task.call_args_list
    endpoint = next(
        handler
        for task_name, handler in (call.args for call in register_calls)
        if task_name.endswith(".track")
    )

    result = endpoint("payload")

    application_context_mock.clear_context.assert_called_once()
    assert container_mock.get.call_count >= 2
    assert tracking_handler.calls == ["payload"]
    assert result == "payload"
