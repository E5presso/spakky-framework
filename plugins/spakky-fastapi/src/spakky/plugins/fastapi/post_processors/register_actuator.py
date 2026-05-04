"""Post-processor for registering actuator HTTP endpoints."""

from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus

from spakky.actuator.result import (
    ActuatorHealthResult,
    ActuatorInfoResult,
    HealthStatus,
)
from spakky.actuator.service import ActuatorAggregationService
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from typing import override

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig


@Order(0)
@Pod()
class RegisterActuatorPostProcessor(IPostProcessor, IContainerAware):
    """Register actuator endpoints when the actuator service is available."""

    __container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        """Set the container used to resolve actuator dependencies."""
        self.__container = container

    @override
    def post_process(self, pod: object) -> object:
        """Register actuator routes on FastAPI instances."""
        if not isinstance(pod, FastAPI):
            return pod

        service = self.__container.get_or_none(ActuatorAggregationService)
        if service is None:
            return pod

        config = self.__container.get_or_none(FastAPIActuatorConfig)
        if config is None:
            config = FastAPIActuatorConfig()
        if not config.enabled:
            return pod

        self._register_routes(pod, service, config)
        return pod

    def _register_routes(
        self,
        fast_api: FastAPI,
        service: ActuatorAggregationService,
        config: FastAPIActuatorConfig,
    ) -> None:
        if config.health_enabled:
            self._add_health_route(
                fast_api,
                f"{config.base_path}/health",
                service.evaluate_health_async,
            )
        if config.readiness_enabled:
            self._add_health_route(
                fast_api,
                f"{config.base_path}/readiness",
                service.evaluate_readiness_async,
            )
        if config.liveness_enabled:
            self._add_health_route(
                fast_api,
                f"{config.base_path}/liveness",
                service.evaluate_liveness_async,
            )
        if config.info_enabled:
            self._add_info_route(
                fast_api,
                f"{config.base_path}/info",
                service.evaluate_info_async,
            )

    def _add_health_route(
        self,
        fast_api: FastAPI,
        path: str,
        evaluator: Callable[[], Awaitable[ActuatorHealthResult]],
    ) -> None:
        async def endpoint() -> JSONResponse:
            result = await evaluator()
            return self._health_response(result)

        fast_api.add_api_route(path=path, endpoint=endpoint, methods=["GET"])

    def _add_info_route(
        self,
        fast_api: FastAPI,
        path: str,
        evaluator: Callable[[], Awaitable[ActuatorInfoResult]],
    ) -> None:
        async def endpoint() -> dict[str, object]:
            result = await evaluator()
            return self._info_payload(result)

        fast_api.add_api_route(path=path, endpoint=endpoint, methods=["GET"])

    def _health_response(self, health_result: ActuatorHealthResult) -> JSONResponse:
        status_code = HTTPStatus.OK
        if health_result.status is HealthStatus.UNHEALTHY:
            status_code = HTTPStatus.SERVICE_UNAVAILABLE
        return JSONResponse(
            content=self._health_payload(health_result),
            status_code=status_code,
        )

    def _health_payload(self, result: ActuatorHealthResult) -> dict[str, object]:
        return {
            "endpoint": result.endpoint.value,
            "status": result.status.value,
            "components": [
                {
                    "name": component.name,
                    "status": component.status.value,
                    "required": component.required,
                    "details": self._mapping_payload(component.details),
                }
                for component in result.components
            ],
        }

    def _info_payload(self, result: ActuatorInfoResult) -> dict[str, object]:
        return {"info": self._mapping_payload(result.info)}

    def _mapping_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return {key: value[key] for key in sorted(value)}
