import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, Generator

import pytest
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.pod.annotations.pod import Pod
from testcontainers.rabbitmq import RabbitMqContainer  # pyrefly: ignore

import spakky_rabbitmq
from spakky_rabbitmq.event.config import RabbitMQConnectionConfig
from tests import apps


@pytest.fixture(name="config", scope="package", params=["test_exchange", None])
def get_config_fixture(
    request: pytest.FixtureRequest,
) -> Generator[RabbitMQConnectionConfig, Any, None]:
    config = RabbitMQConnectionConfig(
        host="localhost",
        port=25672,
        user="test",
        password="test",
        exchange_name=request.param,
    )
    yield config


@pytest.fixture(scope="package", autouse=True)
def rabbitmq_container(config: RabbitMQConnectionConfig) -> Generator[None, None, None]:
    container = RabbitMqContainer(
        image="rabbitmq:management",
        port=config.port,
        username=config.user,
        password=config.password,
    ).with_bind_ports(config.port, config.port)

    with container:
        yield


@pytest.fixture(name="app", scope="function")
def get_app_fixture(
    config: RabbitMQConnectionConfig,
) -> Generator[SpakkyApplication, Any, None]:
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    @Pod(name="config")
    def get_config() -> RabbitMQConnectionConfig:
        return config

    app = (
        SpakkyApplication(ApplicationContext(logger))
        .load_plugins(include={spakky_rabbitmq.PLUGIN_NAME})
        .enable_async_logging()
        .enable_logging()
        .scan(apps)
        .add(get_config)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
