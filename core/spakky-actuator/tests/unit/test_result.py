"""Tests for actuator result contracts."""

from spakky.actuator.result import (
    ActuatorEndpoint,
    ActuatorHealthResult,
    ActuatorInfoResult,
    ComponentHealthResult,
    HealthStatus,
)


def test_component_factory_sorts_details_expect_deterministic_mapping() -> None:
    """component factory가 details key를 정렬하는지 검증한다."""
    result = ComponentHealthResult.healthy("db", details={"z": 1, "a": 2})

    assert list(result.details.keys()) == ["a", "z"]


def test_health_result_with_no_components_expect_healthy_baseline() -> None:
    """component가 없으면 deterministic healthy baseline이 반환되는지 검증한다."""
    result = ActuatorHealthResult.from_components(ActuatorEndpoint.HEALTH, ())

    assert result.endpoint is ActuatorEndpoint.HEALTH
    assert result.status is HealthStatus.HEALTHY
    assert result.components == ()


def test_health_result_required_unhealthy_expect_aggregate_unhealthy() -> None:
    """required component가 unhealthy이면 aggregate도 unhealthy인지 검증한다."""
    result = ActuatorHealthResult.from_components(
        ActuatorEndpoint.READINESS,
        (
            ComponentHealthResult.healthy("cache"),
            ComponentHealthResult.unhealthy("db"),
        ),
    )

    assert result.status is HealthStatus.UNHEALTHY
    assert [component.name for component in result.components] == ["cache", "db"]


def test_health_result_optional_unhealthy_expect_aggregate_healthy() -> None:
    """optional component unhealthy가 aggregate를 실패시키지 않는지 검증한다."""
    result = ActuatorHealthResult.from_components(
        ActuatorEndpoint.HEALTH,
        (ComponentHealthResult.unhealthy("optional", required=False),),
    )

    assert result.status is HealthStatus.HEALTHY


def test_info_result_sorts_keys_expect_deterministic_mapping() -> None:
    """info result가 key를 정렬하는지 검증한다."""
    result = ActuatorInfoResult.from_mapping({"z": 1, "a": 2})

    assert list(result.info.keys()) == ["a", "z"]
