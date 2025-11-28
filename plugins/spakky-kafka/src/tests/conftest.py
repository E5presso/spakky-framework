import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any, Generator

import pytest
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from testcontainers.kafka import KafkaContainer  # pyrefly: ignore  # type: ignore

import spakky_kafka
from spakky_kafka.common.config import AutoOffsetResetType
from spakky_kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX
from tests import apps


@pytest.fixture(name="port", scope="package")
def port_fixture() -> int:
    return 9093


@pytest.fixture(name="environment_variables", scope="package", autouse=True)
def setup_environment_variables_fixture(port: int) -> Generator[None, Any, None]:
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = f"localhost:{port}"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = (
        AutoOffsetResetType.EARLIEST.value
    )
    yield


@pytest.fixture(scope="package", autouse=True)
def kafka_container(
    port: int, environment_variables: None
) -> Generator[None, None, None]:
    bootstrap_servers = environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"]

    container = (
        KafkaContainer(port=port)
        .with_env("KAFKA_NODE_ID", "1")
        .with_env("KAFKA_ADVERTISED_LISTENERS", bootstrap_servers)
        .with_bind_ports(port, port)
    )

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
        .load_plugins(include={spakky_kafka.PLUGIN_NAME})
        .enable_async_logging()
        .enable_logging()
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
