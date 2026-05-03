"""Tests for actuator aggregation service."""

from collections.abc import Mapping

import pytest
from spakky.actuator.config import ActuatorConfig
from spakky.actuator.error import CannotEvaluateAsyncExtensionSynchronouslyError
from spakky.actuator.interfaces.contributor import (
    AbstractAsyncInfoContributor,
    AbstractInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.result import (
    ActuatorEndpoint,
    ComponentHealthResult,
    HealthStatus,
)
from spakky.actuator.service import ActuatorAggregationService


class _Probe(AbstractHealthProbe):
    _name: str
    _result: ComponentHealthResult
    _endpoints: tuple[ActuatorEndpoint, ...]

    def __init__(
        self,
        name: str,
        result: ComponentHealthResult,
        endpoints: tuple[ActuatorEndpoint, ...] = (
            ActuatorEndpoint.HEALTH,
            ActuatorEndpoint.READINESS,
        ),
    ) -> None:
        self._name = name
        self._result = result
        self._endpoints = endpoints

    @property
    def name(self) -> str:
        return self._name

    @property
    def required(self) -> bool:
        return self._result.required

    @property
    def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
        return self._endpoints

    def check(self) -> ComponentHealthResult:
        return self._result


class _FailingProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "failing"

    def check(self) -> ComponentHealthResult:
        raise RuntimeError("boom")


class _AsyncProbe(AbstractAsyncHealthProbe):
    _name: str
    _should_fail: bool

    def __init__(self, name: str = "async", should_fail: bool = False) -> None:
        self._name = name
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    async def check_async(self) -> ComponentHealthResult:
        if self._should_fail:
            raise RuntimeError("async boom")
        return ComponentHealthResult.healthy(self.name)


class _Contributor(AbstractInfoContributor):
    _name: str
    _payload: Mapping[str, object]

    def __init__(self, name: str, payload: Mapping[str, object]) -> None:
        self._name = name
        self._payload = payload

    @property
    def name(self) -> str:
        return self._name

    def contribute_info(self) -> Mapping[str, object]:
        return self._payload


class _AsyncContributor(AbstractAsyncInfoContributor):
    @property
    def name(self) -> str:
        return "async"

    async def contribute_info_async(self) -> Mapping[str, object]:
        return {"async": True}


def test_no_custom_probes_expect_health_readiness_liveness_baseline() -> None:
    """custom probe가 없으면 health/readiness/liveness baseline healthy인지 검증한다."""
    service = ActuatorAggregationService(ActuatorExtensionRegistry())

    assert service.evaluate_health().status is HealthStatus.HEALTHY
    assert service.evaluate_readiness().status is HealthStatus.HEALTHY
    assert service.evaluate_liveness().status is HealthStatus.HEALTHY


def test_probe_defaults_expect_required_for_health_and_readiness() -> None:
    """probe default가 required이며 health/readiness endpoint를 대상으로 하는지 검증한다."""
    probe = _AsyncProbe()

    assert probe.required is True
    assert probe.endpoints == (ActuatorEndpoint.HEALTH, ActuatorEndpoint.READINESS)


def test_required_unhealthy_probe_expect_health_and_readiness_unhealthy() -> None:
    """required unhealthy probe가 health/readiness aggregate를 실패시키는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_health_probe(_Probe("db", ComponentHealthResult.unhealthy("db")))
    service = ActuatorAggregationService(registry)

    health = service.evaluate_health()
    readiness = service.evaluate_readiness()

    assert health.status is HealthStatus.UNHEALTHY
    assert readiness.status is HealthStatus.UNHEALTHY
    assert health.components[0].name == "db"
    assert readiness.components[0].name == "db"


def test_liveness_uses_only_liveness_probes_expect_readiness_isolated() -> None:
    """liveness가 readiness 전용 probe 실패와 분리되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_health_probe(_Probe("db", ComponentHealthResult.unhealthy("db")))
    registry.register_health_probe(
        _Probe(
            "process",
            ComponentHealthResult.healthy("process"),
            endpoints=(ActuatorEndpoint.LIVENESS,),
        )
    )
    service = ActuatorAggregationService(registry)

    assert service.evaluate_readiness().status is HealthStatus.UNHEALTHY
    assert service.evaluate_liveness().status is HealthStatus.HEALTHY
    assert service.evaluate_liveness().components[0].name == "process"


def test_probe_exception_expect_unhealthy_component_with_structured_error() -> None:
    """probe exception이 structured error details를 가진 unhealthy component가 되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_health_probe(_FailingProbe())
    service = ActuatorAggregationService(registry)

    result = service.evaluate_health()

    assert result.status is HealthStatus.UNHEALTHY
    assert result.components[0].status is HealthStatus.UNHEALTHY
    assert result.components[0].details == {
        "error": {"message": "boom", "type": "RuntimeError"}
    }


async def test_async_probe_expect_async_evaluation_includes_component() -> None:
    """async probe가 async aggregation에서 평가되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_async_health_probe(_AsyncProbe())
    service = ActuatorAggregationService(registry)

    result = await service.evaluate_health_async()

    assert result.status is HealthStatus.HEALTHY
    assert result.components[0].name == "async"


async def test_async_readiness_and_liveness_expect_endpoint_specific_results() -> None:
    """async readiness/liveness 평가가 endpoint별 component를 반환하는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_async_health_probe(_AsyncProbe("readiness"))
    registry.register_health_probe(
        _Probe(
            "process",
            ComponentHealthResult.healthy("process"),
            endpoints=(ActuatorEndpoint.LIVENESS,),
        )
    )
    service = ActuatorAggregationService(registry)

    readiness = await service.evaluate_readiness_async()
    liveness = await service.evaluate_liveness_async()

    assert readiness.components[0].name == "readiness"
    assert liveness.components[0].name == "process"


async def test_async_probe_exception_expect_structured_error() -> None:
    """async probe exception도 unhealthy component로 변환되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_async_health_probe(_AsyncProbe(should_fail=True))
    service = ActuatorAggregationService(registry)

    result = await service.evaluate_health_async()

    assert result.status is HealthStatus.UNHEALTHY
    assert result.components[0].details == {
        "error": {"message": "async boom", "type": "RuntimeError"}
    }


def test_sync_health_with_async_probe_expect_error() -> None:
    """sync 평가가 async probe를 만나면 명시적 에러를 발생시키는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_async_health_probe(_AsyncProbe())
    service = ActuatorAggregationService(registry)

    with pytest.raises(CannotEvaluateAsyncExtensionSynchronouslyError):
        service.evaluate_health()


def test_info_contributors_expect_deterministic_merge() -> None:
    """info contributor 출력이 이름순으로 deterministic merge되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_info_contributor(_Contributor("b", {"shared": "b", "b": 2}))
    registry.register_info_contributor(_Contributor("a", {"shared": "a", "a": 1}))
    service = ActuatorAggregationService(registry)

    result = service.evaluate_info()

    assert result.info == {"a": 1, "b": 2, "shared": "b"}
    assert list(result.info.keys()) == ["a", "b", "shared"]


async def test_async_info_contributor_expect_merged_output() -> None:
    """async info contributor가 async info aggregation에 포함되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_info_contributor(_Contributor("sync", {"sync": True}))
    registry.register_async_info_contributor(_AsyncContributor())
    service = ActuatorAggregationService(registry)

    result = await service.evaluate_info_async()

    assert result.info == {"async": True, "sync": True}


def test_sync_info_with_async_contributor_expect_error() -> None:
    """sync info 평가가 async contributor를 만나면 명시적 에러를 발생시키는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_async_info_contributor(_AsyncContributor())
    service = ActuatorAggregationService(registry)

    with pytest.raises(CannotEvaluateAsyncExtensionSynchronouslyError):
        service.evaluate_info()


def test_config_without_details_expect_details_removed() -> None:
    """include_details=False이면 component details가 제거되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_health_probe(
        _Probe("db", ComponentHealthResult.unhealthy("db", details={"error": "x"}))
    )
    service = ActuatorAggregationService(
        registry, ActuatorConfig(include_details=False)
    )

    result = service.evaluate_health()

    assert result.components[0].details == {}


def test_config_without_details_expect_healthy_details_removed() -> None:
    """include_details=False이면 healthy component details도 제거되는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    registry.register_health_probe(
        _Probe("db", ComponentHealthResult.healthy("db", details={"ok": True}))
    )
    service = ActuatorAggregationService(
        registry, ActuatorConfig(include_details=False)
    )

    result = service.evaluate_health()

    assert result.components[0].details == {}
