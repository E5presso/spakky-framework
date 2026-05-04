"""Tests for Typer actuator command registration."""

from collections.abc import Generator
from contextlib import contextmanager
import json

from click.testing import Result
from pytest import MonkeyPatch
from collections.abc import Mapping

from spakky.actuator.interfaces.contributor import IInfoContributor
from spakky.actuator.interfaces.probe import AbstractHealthProbe
from spakky.actuator.result import ComponentHealthResult
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.pod.annotations.pod import Pod
from typer import Typer
from typer.testing import CliRunner

import spakky.plugins.typer

EMPTY_STARTUP_INFO = {
    "phase_count": 0,
    "records": [],
    "total_elapsed_seconds": 0,
}


@Pod()
class _CliProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "cli"

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(
            self.name,
            details={"a": 1, "z": 2},
        )


@Pod()
class _CliInfoContributor(IInfoContributor):
    @property
    def name(self) -> str:
        return "cli-info"

    def contribute_info(self) -> Mapping[str, object]:
        return {"app": "typer", "version": "test"}


@Pod(name="cli")
def _get_cli() -> Typer:
    return Typer()


def test_actuator_command_registered_when_actuator_plugin_loaded() -> None:
    """actuator plugin 로드 시 actuator command group이 등록되는지 검증한다."""
    with _actuator_cli() as cli:
        result = CliRunner().invoke(cli, ["actuator", "health"])

    assert result.exit_code == 0


def test_actuator_health_command_outputs_core_status_model() -> None:
    """actuator health command가 core status model을 JSON으로 출력하는지 검증한다."""
    with _actuator_cli() as cli:
        result: Result = CliRunner().invoke(cli, ["actuator", "health"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "components": [
            {
                "details": {"a": 1, "z": 2},
                "name": "cli",
                "required": True,
                "status": "healthy",
            }
        ],
        "endpoint": "health",
        "status": "healthy",
    }


def test_actuator_probe_commands_output_endpoint_statuses() -> None:
    """readiness/liveness command가 endpoint별 core status model을 출력하는지 검증한다."""
    with _actuator_cli() as cli:
        readiness = CliRunner().invoke(cli, ["actuator", "readiness"])
        liveness = CliRunner().invoke(cli, ["actuator", "liveness"])

    assert json.loads(readiness.output)["endpoint"] == "readiness"
    assert json.loads(liveness.output)["endpoint"] == "liveness"


def test_actuator_info_command_outputs_core_info_model() -> None:
    """actuator info command가 core info model을 JSON으로 출력하는지 검증한다."""
    with _actuator_cli() as cli:
        result = CliRunner().invoke(cli, ["actuator", "info"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "info": {
            "app": "typer",
            "startup": EMPTY_STARTUP_INFO,
            "version": "test",
        }
    }


def test_actuator_command_absent_when_config_disabled(
    monkeypatch: MonkeyPatch,
) -> None:
    """config로 비활성화하면 actuator command group이 등록되지 않는지 검증한다."""
    monkeypatch.setenv("SPAKKY_TYPER_ACTUATOR_COMMAND_ENABLED", "false")
    with _actuator_cli() as cli:
        group_names = [group.name for group in cli.registered_groups]

    assert "actuator" not in group_names


def test_actuator_command_uses_configured_group_name(
    monkeypatch: MonkeyPatch,
) -> None:
    """config로 지정한 actuator command group 이름을 사용한다."""
    monkeypatch.setenv("SPAKKY_TYPER_ACTUATOR_COMMAND_NAME", "status")
    with _actuator_cli() as cli:
        result = CliRunner().invoke(cli, ["status", "health"])

    assert result.exit_code == 0
    assert json.loads(result.output)["endpoint"] == "health"


@contextmanager
def _actuator_cli() -> Generator[Typer, None, None]:
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.plugins.typer.PLUGIN_NAME,
                Plugin(name="spakky-actuator"),
            }
        )
        .add(_get_cli)
        .add(_CliProbe)
        .add(_CliInfoContributor)
    )
    app.start()
    try:
        yield app.container.get(type_=Typer)
    finally:
        app.stop()
