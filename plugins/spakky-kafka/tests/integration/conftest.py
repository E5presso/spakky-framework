import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any
from collections.abc import Generator

import pytest
import spakky.tracing
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from testcontainers.kafka import (
    KafkaContainer,  # type: ignore[import-untyped]  # testcontainers lacks type stubs
)

import spakky.plugins.kafka
from spakky.plugins.kafka.common.config import AutoOffsetResetType
from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX
from tests import apps


@pytest.fixture(name="environment_variables", scope="package", autouse=True)
def setup_environment_variables_fixture() -> Generator[None, Any, None]:
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test"
    if bootstrap_servers := environ.get("SPAKKY_KAFKA_TEST_BOOTSTRAP_SERVERS"):
        environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = (
            bootstrap_servers
        )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = (
        AutoOffsetResetType.EARLIEST.value
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}POLL_TIMEOUT"] = "0.1"
    yield


@pytest.fixture(scope="package", autouse=True)
def kafka_container(environment_variables: None) -> Generator[None, None, None]:
    """Each xdist worker owns a broker with a Docker-allocated host port."""
    if environ.get("SPAKKY_KAFKA_TEST_BOOTSTRAP_SERVERS"):
        yield
        return
    with KafkaContainer() as container:
        environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = (
            container.get_bootstrap_server()
        )
        yield


@pytest.fixture(name="app", scope="package")
def get_app_fixture() -> Generator[SpakkyApplication, Any, None]:
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.plugins.kafka.PLUGIN_NAME,
                spakky.tracing.PLUGIN_NAME,
            }
        )
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
