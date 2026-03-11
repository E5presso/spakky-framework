"""Tests for CeleryConfig."""

import os

import pytest
from pydantic import ValidationError

from spakky.plugins.celery.common.config import CeleryConfig


def test_celery_config_requires_broker_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """CeleryConfig가 broker_url 필수 필드를 요구하는지 검증한다."""
    monkeypatch.delenv("SPAKKY_CELERY__BROKER_URL", raising=False)
    with pytest.raises(ValidationError):
        CeleryConfig()


def test_celery_config_default_values() -> None:
    """CeleryConfig가 선택적 필드의 기본값으로 올바르게 초기화되는지 검증한다."""
    os.environ["SPAKKY_CELERY__BROKER_URL"] = "amqp://test:test@localhost:5672//"
    try:
        config = CeleryConfig()

        assert config.broker_url == "amqp://test:test@localhost:5672//"
        assert config.result_backend is None
        assert config.task_serializer == "json"
        assert config.result_serializer == "json"
        assert config.accept_content == ["json"]
        assert config.timezone == "UTC"
        assert config.enable_utc is True
    finally:
        del os.environ["SPAKKY_CELERY__BROKER_URL"]


def test_celery_config_from_environment_variables() -> None:
    """CeleryConfig가 환경변수에서 설정값을 로드하는지 검증한다."""
    os.environ["SPAKKY_CELERY__BROKER_URL"] = "redis://localhost:6379/0"
    os.environ["SPAKKY_CELERY__RESULT_BACKEND"] = "redis://localhost:6379/1"
    os.environ["SPAKKY_CELERY__TASK_SERIALIZER"] = "pickle"
    os.environ["SPAKKY_CELERY__TIMEZONE"] = "Asia/Seoul"
    os.environ["SPAKKY_CELERY__ENABLE_UTC"] = "false"
    try:
        config = CeleryConfig()

        assert config.broker_url == "redis://localhost:6379/0"
        assert config.result_backend == "redis://localhost:6379/1"
        assert config.task_serializer == "pickle"
        assert config.timezone == "Asia/Seoul"
        assert config.enable_utc is False
    finally:
        del os.environ["SPAKKY_CELERY__BROKER_URL"]
        del os.environ["SPAKKY_CELERY__RESULT_BACKEND"]
        del os.environ["SPAKKY_CELERY__TASK_SERIALIZER"]
        del os.environ["SPAKKY_CELERY__TIMEZONE"]
        del os.environ["SPAKKY_CELERY__ENABLE_UTC"]


def test_celery_config_rejects_invalid_timezone() -> None:
    """CeleryConfig가 유효하지 않은 timezone을 거부하는지 검증한다."""
    os.environ["SPAKKY_CELERY__BROKER_URL"] = "amqp://test:test@localhost:5672//"
    os.environ["SPAKKY_CELERY__TIMEZONE"] = "Invalid/Timezone"
    try:
        with pytest.raises(ValidationError) as exc_info:
            CeleryConfig()
        assert "Invalid timezone" in str(exc_info.value)
    finally:
        del os.environ["SPAKKY_CELERY__BROKER_URL"]
        del os.environ["SPAKKY_CELERY__TIMEZONE"]
