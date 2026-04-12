import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any, Generator

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from testcontainers.rabbitmq import (
    RabbitMqContainer,  # type: ignore[import-untyped]  # testcontainers lacks type stubs
)

import spakky.plugins.rabbitmq
from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX
from tests import apps


@pytest.fixture(name="environment_variables", scope="package", autouse=True)
def setup_environment_variables_fixture() -> Generator[None, Any, None]:
    """RabbitMQ 테스트를 위한 환경 변수 설정 및 정리."""
    env_updates = {
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL": "false",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST": "localhost",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT": str(25672),
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USER": "test",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD": "test",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME": "test_exchange",
    }
    previous_values = {key: environ.get(key) for key in env_updates}

    for key, value in env_updates.items():
        environ[key] = value

    try:
        yield
    finally:
        for key, previous_value in previous_values.items():
            if previous_value is None:
                environ.pop(key, None)
            else:
                environ[key] = previous_value


@pytest.fixture(scope="package", autouse=True)
def rabbitmq_container(environment_variables: None) -> Generator[None, None, None]:
    """RabbitMQ 테스트 컨테이너 실행 및 정리."""
    port = int(environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"])
    username = environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"]
    password = environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"]

    container = RabbitMqContainer(
        port=port,
        username=username,
        password=password,
    ).with_bind_ports(port, port)

    with container:
        yield


@pytest.fixture(name="app", scope="package")
def get_app_fixture() -> Generator[SpakkyApplication, Any, None]:
    """RabbitMQ 플러그인이 로드된 Spakky 애플리케이션 생성."""
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
                spakky.plugins.rabbitmq.PLUGIN_NAME,
            }
        )
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
