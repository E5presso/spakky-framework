"""Tests for Typer plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from typer import Typer

from spakky.plugins.typer.actuator import ActuatorTyperCommandPostProcessor
from spakky.plugins.typer.main import initialize
from spakky.plugins.typer.post_processor import TyperCLIPostProcessor


@Pod(name="custom_cli")
def _custom_cli() -> Typer:
    return Typer(name="custom")


def test_initialize_registers_default_typer_app() -> None:
    """initialize가 별도 Typer Pod 없이도 기본 Typer 앱을 등록하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)
    app.start()
    try:
        cli = app.container.get(Typer)
        assert isinstance(cli, Typer)
        assert "typer_app" in app.container.pods
        assert app.container.contains(TyperCLIPostProcessor)
        assert app.container.contains(ActuatorTyperCommandPostProcessor)
    finally:
        app.stop()


def test_initialize_keeps_pre_registered_custom_typer_app() -> None:
    """이미 등록된 Typer Pod가 있으면 기본 Typer 앱을 추가하지 않는다."""
    app = SpakkyApplication(ApplicationContext()).add(_custom_cli)

    initialize(app)
    app.start()
    try:
        cli = app.container.get(Typer)
        assert cli.info.name == "custom"
        assert "typer_app" not in app.container.pods
    finally:
        app.stop()
