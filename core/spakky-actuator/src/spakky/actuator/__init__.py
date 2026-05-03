"""Transport-neutral actuator contracts and aggregation services."""

from spakky.actuator.config import ActuatorConfig
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
    ActuatorHealthResult,
    ActuatorInfoResult,
    ComponentHealthResult,
    HealthStatus,
)
from spakky.actuator.service import ActuatorAggregationService

__all__ = [
    "AbstractAsyncHealthProbe",
    "AbstractAsyncInfoContributor",
    "AbstractHealthProbe",
    "AbstractInfoContributor",
    "ActuatorAggregationService",
    "ActuatorConfig",
    "ActuatorEndpoint",
    "ActuatorExtensionRegistry",
    "ActuatorHealthResult",
    "ActuatorInfoResult",
    "ComponentHealthResult",
    "HealthStatus",
]
