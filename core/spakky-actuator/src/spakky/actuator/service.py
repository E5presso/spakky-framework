"""Actuator aggregation service."""

from collections.abc import Mapping

from spakky.core.pod.annotations.pod import Pod

from spakky.actuator.config import ActuatorConfig
from spakky.actuator.error import CannotEvaluateAsyncExtensionSynchronouslyError
from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.result import (
    ActuatorEndpoint,
    ActuatorHealthResult,
    ActuatorInfoResult,
    ComponentHealthResult,
)


@Pod()
class ActuatorAggregationService:
    """Aggregate health probes and info contributors into actuator results."""

    _registry: ActuatorExtensionRegistry
    _config: ActuatorConfig

    def __init__(
        self,
        registry: ActuatorExtensionRegistry,
        config: ActuatorConfig | None = None,
    ) -> None:
        """Initialize the aggregation service."""
        self._registry = registry
        self._config = ActuatorConfig() if config is None else config

    def evaluate_health(self) -> ActuatorHealthResult:
        """Evaluate the health endpoint synchronously."""
        return self._evaluate_sync(ActuatorEndpoint.HEALTH)

    def evaluate_readiness(self) -> ActuatorHealthResult:
        """Evaluate the readiness endpoint synchronously."""
        return self._evaluate_sync(ActuatorEndpoint.READINESS)

    def evaluate_liveness(self) -> ActuatorHealthResult:
        """Evaluate the liveness endpoint synchronously."""
        return self._evaluate_sync(ActuatorEndpoint.LIVENESS)

    async def evaluate_health_async(self) -> ActuatorHealthResult:
        """Evaluate the health endpoint asynchronously."""
        return await self._evaluate_async(ActuatorEndpoint.HEALTH)

    async def evaluate_readiness_async(self) -> ActuatorHealthResult:
        """Evaluate the readiness endpoint asynchronously."""
        return await self._evaluate_async(ActuatorEndpoint.READINESS)

    async def evaluate_liveness_async(self) -> ActuatorHealthResult:
        """Evaluate the liveness endpoint asynchronously."""
        return await self._evaluate_async(ActuatorEndpoint.LIVENESS)

    def evaluate_info(self) -> ActuatorInfoResult:
        """Evaluate synchronous info contributors."""
        if self._matching_async_info_contributors():
            raise CannotEvaluateAsyncExtensionSynchronouslyError()
        return ActuatorInfoResult.from_mapping(
            self._merge_info(self._registry.info_contributors())
        )

    async def evaluate_info_async(self) -> ActuatorInfoResult:
        """Evaluate sync and async info contributors."""
        info = self._merge_info(self._registry.info_contributors())
        for contributor in self._registry.async_info_contributors():
            info.update(await contributor.contribute_info_async())
        return ActuatorInfoResult.from_mapping(info)

    def _evaluate_sync(self, endpoint: ActuatorEndpoint) -> ActuatorHealthResult:
        if self._matching_async_health_probes(endpoint):
            raise CannotEvaluateAsyncExtensionSynchronouslyError()
        components = tuple(
            self._check_sync_probe(probe)
            for probe in self._matching_health_probes(endpoint)
        )
        return ActuatorHealthResult.from_components(endpoint, components)

    async def _evaluate_async(self, endpoint: ActuatorEndpoint) -> ActuatorHealthResult:
        sync_components = tuple(
            self._check_sync_probe(probe)
            for probe in self._matching_health_probes(endpoint)
        )
        async_components = []
        for probe in self._matching_async_health_probes(endpoint):
            async_components.append(await self._check_async_probe(probe))
        return ActuatorHealthResult.from_components(
            endpoint,
            sync_components + tuple(async_components),
        )

    def _matching_health_probes(
        self, endpoint: ActuatorEndpoint
    ) -> tuple[AbstractHealthProbe, ...]:
        return tuple(
            probe
            for probe in self._registry.health_probes()
            if endpoint in probe.endpoints
        )

    def _matching_async_health_probes(
        self, endpoint: ActuatorEndpoint
    ) -> tuple[AbstractAsyncHealthProbe, ...]:
        return tuple(
            probe
            for probe in self._registry.async_health_probes()
            if endpoint in probe.endpoints
        )

    def _matching_async_info_contributors(
        self,
    ) -> tuple[IAsyncInfoContributor, ...]:
        return self._registry.async_info_contributors()

    def _check_sync_probe(self, probe: AbstractHealthProbe) -> ComponentHealthResult:
        try:
            return self._apply_details_policy(probe.check())
        except Exception as exception:
            return self._exception_result(probe.name, probe.required, exception)

    async def _check_async_probe(
        self, probe: AbstractAsyncHealthProbe
    ) -> ComponentHealthResult:
        try:
            return self._apply_details_policy(await probe.check_async())
        except Exception as exception:
            return self._exception_result(probe.name, probe.required, exception)

    def _exception_result(
        self, name: str, required: bool, exception: Exception
    ) -> ComponentHealthResult:
        return self._apply_details_policy(
            ComponentHealthResult.unhealthy(
                name,
                required=required,
                details={
                    "error": {
                        "message": str(exception),
                        "type": exception.__class__.__name__,
                    }
                },
            )
        )

    def _apply_details_policy(
        self, result: ComponentHealthResult
    ) -> ComponentHealthResult:
        if self._config.include_details:
            return result
        if result.status.value == "healthy":
            return ComponentHealthResult.healthy(result.name, required=result.required)
        return ComponentHealthResult.unhealthy(result.name, required=result.required)

    def _merge_info(
        self, contributors: tuple[IInfoContributor, ...]
    ) -> dict[str, object]:
        info: dict[str, object] = {}
        for contributor in contributors:
            self._merge_info_payload(info, contributor.contribute_info())
        return info

    def _merge_info_payload(
        self,
        target: dict[str, object],
        payload: Mapping[str, object],
    ) -> None:
        for key in sorted(payload):
            target[key] = payload[key]
