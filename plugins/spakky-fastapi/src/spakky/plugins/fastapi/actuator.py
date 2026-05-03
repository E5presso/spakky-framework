"""FastAPI configuration for actuator HTTP endpoints."""

from spakky.core.stereotype.configuration import Configuration


@Configuration()
class FastAPIActuatorConfig:
    """Configuration for FastAPI actuator endpoint exposure."""

    enabled: bool
    base_path: str
    health_enabled: bool
    readiness_enabled: bool
    liveness_enabled: bool
    info_enabled: bool

    def __init__(
        self,
        *,
        enabled: bool = True,
        base_path: str = "/actuator",
        health_enabled: bool = True,
        readiness_enabled: bool = True,
        liveness_enabled: bool = True,
        info_enabled: bool = True,
    ) -> None:
        """Initialize actuator endpoint exposure configuration."""
        self.enabled = enabled
        self.base_path = self._normalize_base_path(base_path)
        self.health_enabled = health_enabled
        self.readiness_enabled = readiness_enabled
        self.liveness_enabled = liveness_enabled
        self.info_enabled = info_enabled

    def _normalize_base_path(self, base_path: str) -> str:
        stripped = base_path.strip("/")
        if not stripped:
            return ""
        return f"/{stripped}"
