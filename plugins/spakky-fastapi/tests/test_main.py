"""FastAPI plugin initialization tests."""

from fastapi import FastAPI
from pytest import MonkeyPatch
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.fastapi.config import (
    SPAKKY_FASTAPI_CONFIG_ENV_PREFIX,
    FastAPIConfig,
)

import spakky.plugins.fastapi


def test_initialize_registers_default_fastapi_app(
    monkeypatch: MonkeyPatch,
) -> None:
    """플러그인은 FastAPI Pod가 없으면 기본 앱을 등록한다."""
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}TITLE", "Orders API")
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}VERSION", "1.2.3")
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}DEBUG", "true")

    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={spakky.plugins.fastapi.PLUGIN_NAME}
    )

    assert "fastapi_app" in app.container.pods

    app.start()
    fast_api = app.container.get(FastAPI)

    assert fast_api.title == "Orders API"
    assert fast_api.version == "1.2.3"
    assert fast_api.debug is True


def test_initialize_keeps_pre_registered_custom_fastapi_app() -> None:
    """사용자가 먼저 FastAPI Pod를 등록하면 플러그인은 기본 앱을 중복 등록하지 않는다."""

    @Pod(name="custom_fastapi")
    def custom_fastapi() -> FastAPI:
        return FastAPI(title="Custom API")

    app = (
        SpakkyApplication(ApplicationContext())
        .add(custom_fastapi)
        .load_plugins(include={spakky.plugins.fastapi.PLUGIN_NAME})
    )

    assert "fastapi_app" not in app.container.pods

    app.start()
    fast_api = app.container.get(FastAPI)

    assert fast_api.title == "Custom API"


def test_fastapi_config_uses_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    """FastAPIConfig는 SPAKKY_FASTAPI_* 환경변수를 읽는다."""
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}TITLE", "Env API")
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}DESCRIPTION", "env docs")
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}VERSION", "9.9.9")
    monkeypatch.setenv(f"{SPAKKY_FASTAPI_CONFIG_ENV_PREFIX}DEBUG", "true")

    config = FastAPIConfig()

    assert config.title == "Env API"
    assert config.description == "env docs"
    assert config.version == "9.9.9"
    assert config.debug is True
