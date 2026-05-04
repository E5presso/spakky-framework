"""Actuator endpoint registration tests."""

from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.testclient import TestClient
from spakky.actuator.interfaces.contributor import IInfoContributor
from spakky.actuator.interfaces.probe import AbstractHealthProbe
from spakky.actuator.result import ActuatorEndpoint, ComponentHealthResult
from spakky.actuator.service import ActuatorAggregationService
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.fastapi.post_processors.register_actuator import (
    RegisterActuatorPostProcessor,
)
from typing import cast
from typing import override
from unittest.mock import Mock

import spakky.plugins.fastapi
from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig

ACTUATOR_PLUGIN_NAME = Plugin(name="spakky-actuator")
EMPTY_STARTUP_INFO = {
    "phase_count": 0,
    "records": [],
    "total_elapsed_seconds": 0,
}


def _start_app(config: FastAPIActuatorConfig | None = None) -> FastAPI:
    @Pod(name="api")
    def get_api() -> FastAPI:
        return FastAPI(debug=True)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                ACTUATOR_PLUGIN_NAME,
                spakky.plugins.fastapi.PLUGIN_NAME,
            }
        )
        .add(get_api)
    )
    if config is not None:

        @Pod(name="fastapi_actuator_config")
        def get_actuator_config() -> FastAPIActuatorConfig:
            return config

        app.add(get_actuator_config)

    app.start()
    return app.container.get(type_=FastAPI)


def test_actuator_routes_registered_when_plugins_loaded() -> None:
    """actuator와 FastAPI 플러그인이 로드되면 표준 actuator route가 등록된다."""
    api = _start_app()

    with TestClient(api) as client:
        health = client.get("/actuator/health")
        readiness = client.get("/actuator/readiness")
        liveness = client.get("/actuator/liveness")
        info = client.get("/actuator/info")

    assert health.status_code == HTTPStatus.OK
    assert readiness.status_code == HTTPStatus.OK
    assert liveness.status_code == HTTPStatus.OK
    assert info.status_code == HTTPStatus.OK
    assert health.json()["status"] == "healthy"
    assert info.json() == {"info": {"startup": EMPTY_STARTUP_INFO}}


def test_actuator_endpoints_output_core_public_result_shape() -> None:
    """FastAPI actuator endpoint가 core result shape를 HTTP payload로 노출한다."""

    @Pod()
    class HttpProbe(AbstractHealthProbe):
        @property
        @override
        def name(self) -> str:
            return "http"

        @override
        def check(self) -> ComponentHealthResult:
            return ComponentHealthResult.healthy(
                self.name,
                details={"a": 1, "z": 2},
            )

    @Pod()
    class HttpInfoContributor(IInfoContributor):
        @property
        @override
        def name(self) -> str:
            return "http-info"

        @override
        def contribute_info(self) -> Mapping[str, object]:
            return {"app": "fastapi", "version": "test"}

    @Pod(name="api")
    def get_api() -> FastAPI:
        return FastAPI(debug=True)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                ACTUATOR_PLUGIN_NAME,
                spakky.plugins.fastapi.PLUGIN_NAME,
            }
        )
        .add(get_api)
        .add(HttpProbe)
        .add(HttpInfoContributor)
    )
    app.start()
    api = app.container.get(type_=FastAPI)

    with TestClient(api) as client:
        health = client.get("/actuator/health")
        info = client.get("/actuator/info")

    assert health.json() == {
        "endpoint": "health",
        "status": "healthy",
        "components": [
            {
                "name": "http",
                "status": "healthy",
                "required": True,
                "details": {"a": 1, "z": 2},
            }
        ],
    }
    assert info.json() == {
        "info": {
            "app": "fastapi",
            "startup": EMPTY_STARTUP_INFO,
            "version": "test",
        }
    }


def test_disabled_actuator_endpoint_is_not_registered() -> None:
    """비활성화된 actuator endpoint는 FastAPI route로 노출되지 않는다."""
    api = _start_app(FastAPIActuatorConfig(readiness_enabled=False))

    with TestClient(api) as client:
        readiness = client.get("/actuator/readiness")
        health = client.get("/actuator/health")

    assert readiness.status_code == HTTPStatus.NOT_FOUND
    assert health.status_code == HTTPStatus.OK


def test_disabled_actuator_endpoint_group_uses_configured_base_path() -> None:
    """config가 비활성화한 endpoint 묶음은 등록되지 않고 base path는 정규화된다."""
    api = _start_app(
        FastAPIActuatorConfig(
            base_path="/",
            health_enabled=False,
            liveness_enabled=False,
            info_enabled=False,
        )
    )

    with TestClient(api) as client:
        readiness = client.get("/readiness")
        health = client.get("/health")
        liveness = client.get("/liveness")
        info = client.get("/info")

    assert readiness.status_code == HTTPStatus.OK
    assert health.status_code == HTTPStatus.NOT_FOUND
    assert liveness.status_code == HTTPStatus.NOT_FOUND
    assert info.status_code == HTTPStatus.NOT_FOUND


def test_disabled_actuator_integration_registers_no_routes() -> None:
    """actuator HTTP exposure가 꺼져 있으면 표준 route가 등록되지 않는다."""
    api = _start_app(FastAPIActuatorConfig(enabled=False))

    with TestClient(api) as client:
        health = client.get("/actuator/health")

    assert health.status_code == HTTPStatus.NOT_FOUND


def test_actuator_post_processor_ignores_non_fastapi_pods() -> None:
    """FastAPI 인스턴스가 아닌 pod는 actuator 등록 대상이 아니다."""
    processor = _make_processor(None)
    pod = object()

    assert processor.post_process(pod) is pod


def test_actuator_post_processor_ignores_fastapi_without_actuator_service() -> None:
    """actuator service가 없으면 FastAPI route를 등록하지 않는다."""
    processor = _make_processor(None)
    api = FastAPI()

    assert processor.post_process(api) is api
    with TestClient(api) as client:
        response = client.get("/actuator/health")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_unhealthy_readiness_returns_service_unavailable() -> None:
    """readiness 결과가 unhealthy이면 HTTP 실패 상태로 응답한다."""

    @Pod()
    class UnhealthyReadinessProbe(AbstractHealthProbe):
        @property
        @override
        def name(self) -> str:
            return "database"

        @property
        @override
        def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
            return (ActuatorEndpoint.READINESS,)

        @override
        def check(self) -> ComponentHealthResult:
            return ComponentHealthResult.unhealthy(self.name)

    @Pod(name="api")
    def get_api() -> FastAPI:
        return FastAPI(debug=True)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                ACTUATOR_PLUGIN_NAME,
                spakky.plugins.fastapi.PLUGIN_NAME,
            }
        )
        .add(get_api)
        .add(UnhealthyReadinessProbe)
    )
    app.start()
    api = app.container.get(type_=FastAPI)

    with TestClient(api) as client:
        response = client.get("/actuator/readiness")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["status"] == "unhealthy"
    assert response.json()["components"][0]["name"] == "database"


def _make_processor(
    service: ActuatorAggregationService | None,
) -> RegisterActuatorPostProcessor:
    container = Mock(spec=IContainer)
    container.get_or_none.return_value = service
    processor = RegisterActuatorPostProcessor()
    processor.set_container(cast(IContainer, container))
    return processor
