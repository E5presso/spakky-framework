"""Tests for main.py initialize function."""

from collections.abc import Generator

import pytest
from celery import Celery
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.celery.aspects.task_dispatch import (
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.config import SPAKKY_CELERY_CONFIG_ENV_PREFIX
from spakky.plugins.celery.main import initialize
from spakky.plugins.celery.post_processor import CeleryPostProcessor


@pytest.fixture(name="celery_environment")
def celery_environment_fixture(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Configure the minimal environment needed by the default Celery app."""
    monkeypatch.setenv(f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}BROKER_URL", "memory://")
    monkeypatch.setenv(f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}APP_NAME", "spakky-test")
    yield


@Pod(name="custom_celery")
def _custom_celery() -> Celery:
    return Celery(main="custom", broker="memory://")


def test_initialize_registers_default_celery_app(
    celery_environment: None,
) -> None:
    """initialize가 별도 Celery Pod 없이도 기본 Celery 앱을 등록하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)
    app.start()
    try:
        celery = app.container.get(Celery)
        assert celery.main == "spakky-test"
        assert celery.conf.broker_url == "memory://"
        assert celery.conf.task_serializer == "json"
        assert celery.conf.result_serializer == "json"
        assert celery.conf.accept_content == ["json"]
        assert app.container.contains(CeleryPostProcessor)
        assert app.container.contains(CeleryTaskDispatchAspect)
        assert app.container.contains(AsyncCeleryTaskDispatchAspect)
    finally:
        app.stop()


def test_initialize_keeps_pre_registered_custom_celery_app() -> None:
    """이미 등록된 Celery Pod가 있으면 기본 앱과 config 강제를 추가하지 않는다."""
    app = SpakkyApplication(ApplicationContext()).add(_custom_celery)

    initialize(app)
    app.start()
    try:
        celery = app.container.get(Celery)
        assert celery.main == "custom"
        assert "celery_app" not in app.container.pods
    finally:
        app.stop()
