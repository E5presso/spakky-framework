"""Tests for actuator plugin initialization."""

from spakky.actuator.config import ActuatorConfig
from spakky.actuator.contributors import StartupReportInfoContributor
from spakky.actuator.interfaces.contributor import IInfoContributor
from spakky.actuator.main import initialize
from spakky.actuator.post_processor import ActuatorExtensionPostProcessor
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.service import ActuatorAggregationService
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_initialize_expect_registers_actuator_pods() -> None:
    """initialize()가 actuator core Pod들을 등록하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    pod_types = {pod.type_ for pod in app.container.pods.values()}
    assert ActuatorConfig in pod_types
    assert ActuatorExtensionRegistry in pod_types
    assert IInfoContributor in pod_types
    assert ActuatorExtensionPostProcessor in pod_types
    assert ActuatorAggregationService in pod_types


def test_initialize_expect_startup_report_contributor_resolves_from_container() -> None:
    """initialize()가 등록한 startup contributor factory가 container에서 실행되는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)

    contributor = app.container.get(IInfoContributor)

    assert isinstance(contributor, StartupReportInfoContributor)
    assert contributor.name == "startup"
