"""Actuator configuration contract."""

from spakky.core.stereotype.configuration import Configuration


@Configuration()
class ActuatorConfig:
    """Configuration for actuator aggregation behavior."""

    include_details: bool

    def __init__(self, include_details: bool = True) -> None:
        """Initialize actuator configuration.

        Args:
            include_details: Whether component details should be exposed.
        """
        self.include_details = include_details
