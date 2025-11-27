import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any, Generator

import pytest
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from testcontainers.rabbitmq import RabbitMqContainer  # pyrefly: ignore  # type: ignore

import spakky_rabbitmq
from tests import apps


@pytest.fixture(
    name="environment_variables",
    scope="package",
    params=["test_exchange", None],
    autouse=True,
)
def setup_environment_variables_fixture(
    request: pytest.FixtureRequest,
) -> Generator[None, Any, None]:
    environ["RABBITMQ__HOST"] = "localhost"
    environ["RABBITMQ__PORT"] = str(25672)
    environ["RABBITMQ__USER"] = "test"
    environ["RABBITMQ__PASSWORD"] = "test"
    if request.param is not None:
        environ["RABBITMQ__EXCHANGE_NAME"] = request.param
    yield


@pytest.fixture(scope="package", autouse=True)
def rabbitmq_container(environment_variables: None) -> Generator[None, None, None]:
    port = int(environ["RABBITMQ__PORT"])
    username = environ["RABBITMQ__USER"]
    password = environ["RABBITMQ__PASSWORD"]

    container = RabbitMqContainer(
        image="rabbitmq:management",
        port=port,
        username=username,
        password=password,
    ).with_bind_ports(port, port)

    with container:
        yield


@pytest.fixture(name="app", scope="function")
def get_app_fixture() -> Generator[SpakkyApplication, Any, None]:
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext(logger))
        .load_plugins(include={spakky_rabbitmq.PLUGIN_NAME})
        .enable_async_logging()
        .enable_logging()
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
