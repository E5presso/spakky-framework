"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.actuator.config import ActuatorConfig
from spakky.actuator.post_processor import ActuatorExtensionPostProcessor
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.service import ActuatorAggregationService


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-actuator plugin.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(ActuatorConfig)
    app.add(ActuatorExtensionRegistry)
    app.add(ActuatorExtensionPostProcessor)
    app.add(ActuatorAggregationService)
