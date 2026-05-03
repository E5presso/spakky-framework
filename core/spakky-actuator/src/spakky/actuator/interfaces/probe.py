"""Health probe extension points."""

from abc import ABC, abstractmethod

from spakky.actuator.result import ActuatorEndpoint, ComponentHealthResult


class AbstractHealthProbe(ABC):
    """Synchronous health probe extension point."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable probe name included in component results."""
        ...

    @property
    def required(self) -> bool:
        """Whether an unhealthy result should fail the aggregate status."""
        return True

    @property
    def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
        """Actuator endpoints evaluated by this probe."""
        return (ActuatorEndpoint.HEALTH, ActuatorEndpoint.READINESS)

    @abstractmethod
    def check(self) -> ComponentHealthResult:
        """Evaluate this probe."""
        ...


class AbstractAsyncHealthProbe(ABC):
    """Asynchronous health probe extension point."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable probe name included in component results."""
        ...

    @property
    def required(self) -> bool:
        """Whether an unhealthy result should fail the aggregate status."""
        return True

    @property
    def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
        """Actuator endpoints evaluated by this probe."""
        return (ActuatorEndpoint.HEALTH, ActuatorEndpoint.READINESS)

    @abstractmethod
    async def check_async(self) -> ComponentHealthResult:
        """Evaluate this probe asynchronously."""
        ...
