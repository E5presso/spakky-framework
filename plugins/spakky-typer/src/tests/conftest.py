import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, Generator

import pytest
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.pod.annotations.pod import Pod
from typer import Typer
from typer.testing import CliRunner

import spakky_typer
from tests import apps


@pytest.fixture(name="name", scope="package")
def get_name_fixture() -> Generator[str, Any, None]:
    name: str = "John"
    yield name


@pytest.fixture(name="cli", scope="function")
def get_cli_fixture(name: str) -> Generator[Typer, Any, None]:
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    @Pod(name="name")
    def get_name() -> str:
        return name

    @Pod(name="cli")
    def get_cli() -> Typer:
        return Typer()

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky_typer.PLUGIN_NAME})
        .enable_async_logging()
        .enable_logging()
        .scan(apps)
        .add(get_name)
        .add(get_cli)
    )
    app.start()

    yield app.container.get(type_=Typer)

    app.stop()
    logger.removeHandler(console)


@pytest.fixture(name="runner", scope="function")
def get_runner_fixture() -> Generator[CliRunner, Any, None]:
    runner: CliRunner = CliRunner()
    yield runner
