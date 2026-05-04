"""Transport-neutral actuator result contracts."""

from collections.abc import Mapping
from dataclasses import field
from enum import StrEnum
from typing import Self

from spakky.core.common.mutability import immutable


class HealthStatus(StrEnum):
    """Aggregate or component health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class ActuatorEndpoint(StrEnum):
    """Transport-neutral actuator endpoint kinds."""

    HEALTH = "health"
    READINESS = "readiness"
    LIVENESS = "liveness"


@immutable
class ComponentHealthResult:
    """Health result for one actuator component."""

    name: str
    status: HealthStatus
    required: bool = True
    details: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def healthy(
        cls,
        name: str,
        *,
        required: bool = True,
        details: Mapping[str, object] | None = None,
    ) -> Self:
        """Create a healthy component result."""
        return cls(
            name=name,
            status=HealthStatus.HEALTHY,
            required=required,
            details=_sorted_mapping(details),
        )

    @classmethod
    def unhealthy(
        cls,
        name: str,
        *,
        required: bool = True,
        details: Mapping[str, object] | None = None,
    ) -> Self:
        """Create an unhealthy component result."""
        return cls(
            name=name,
            status=HealthStatus.UNHEALTHY,
            required=required,
            details=_sorted_mapping(details),
        )


@immutable
class ActuatorHealthResult:
    """Aggregate actuator health result."""

    endpoint: ActuatorEndpoint
    status: HealthStatus
    components: tuple[ComponentHealthResult, ...] = field(default_factory=tuple)

    @classmethod
    def healthy_baseline(cls, endpoint: ActuatorEndpoint) -> Self:
        """Create deterministic healthy baseline result for no probes."""
        return cls(endpoint=endpoint, status=HealthStatus.HEALTHY)

    @classmethod
    def from_components(
        cls,
        endpoint: ActuatorEndpoint,
        components: tuple[ComponentHealthResult, ...],
    ) -> Self:
        """Create aggregate result from component results."""
        ordered_components = tuple(sorted(components, key=lambda item: item.name))
        if not ordered_components:
            return cls.healthy_baseline(endpoint)
        status = HealthStatus.HEALTHY
        for component in ordered_components:
            if component.required and component.status is HealthStatus.UNHEALTHY:
                status = HealthStatus.UNHEALTHY
                break
        return cls(
            endpoint=endpoint,
            status=status,
            components=ordered_components,
        )


@immutable
class ActuatorInfoResult:
    """Transport-neutral actuator info result."""

    info: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, info: Mapping[str, object]) -> Self:
        """Create deterministic info result from a mapping."""
        return cls(info=_sorted_mapping(info))


def _sorted_mapping(values: Mapping[str, object] | None) -> dict[str, object]:
    if values is None:
        return {}
    return {key: values[key] for key in sorted(values)}
