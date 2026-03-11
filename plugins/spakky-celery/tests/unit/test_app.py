"""Tests for CeleryApp."""

import os

from celery import Celery

from spakky.plugins.celery.app import CeleryApp
from spakky.plugins.celery.common.config import CeleryConfig


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


def test_celery_app_creates_celery_instance() -> None:
    """CeleryApp이 Celery 인스턴스를 생성하는지 검증한다."""
    celery_app = _create_celery_app()

    assert isinstance(celery_app.celery, Celery)


def test_celery_app_configures_broker_url() -> None:
    """CeleryApp이 CeleryConfig의 broker_url을 적용하는지 검증한다."""
    config = _create_config(broker_url="redis://localhost:6379/0")
    celery_app = _create_celery_app(config)

    assert celery_app.celery.conf.broker_url == "redis://localhost:6379/0"


def test_celery_app_configures_result_backend() -> None:
    """CeleryApp이 CeleryConfig의 result_backend를 적용하는지 검증한다."""
    config = _create_config()
    celery_app = _create_celery_app(config)

    assert celery_app.celery.conf.result_backend == config.result_backend


def test_celery_app_registers_task() -> None:
    """CeleryApp.register_task()가 태스크를 등록하는지 검증한다."""
    celery_app = _create_celery_app()

    def sample_task() -> str:
        return "done"

    celery_app.register_task("test.sample_task", sample_task)

    assert "test.sample_task" in celery_app.task_routes
