"""Plugin initialization entry point."""

from collections.abc import Callable

from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod

from spakky.actuator.config import ActuatorConfig
from spakky.actuator.contributors import StartupReportInfoContributor
from spakky.actuator.interfaces.contributor import IInfoContributor
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
    app.add(_startup_report_info_contributor(app))
    app.add(ActuatorExtensionPostProcessor)
    app.add(ActuatorAggregationService)


def _startup_report_info_contributor(
    app: SpakkyApplication,
) -> Callable[[], IInfoContributor]:
    @Pod()
    def startup_report_info_contributor() -> IInfoContributor:
        return StartupReportInfoContributor(lambda: app.startup_report)

    return startup_report_info_contributor
