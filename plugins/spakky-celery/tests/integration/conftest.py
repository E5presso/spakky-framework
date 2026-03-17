"""Integration test fixtures for spakky-celery plugin.

Uses testcontainers for RabbitMQ broker and celery.contrib.testing.worker
for running a real Celery worker in a thread.
"""

import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any, Generator

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from testcontainers.rabbitmq import RabbitMqContainer  # type: ignore[import-untyped]

import spakky.plugins.celery
from spakky.plugins.celery.common.config import (
    SPAKKY_CELERY_CONFIG_ENV_PREFIX,
    CeleryConfig,
)
from tests import apps
from tests.apps.dummy import execution_record

RABBITMQ_USER = "test"
RABBITMQ_PASSWORD = "test"
RABBITMQ_INTERNAL_PORT = 5672


@pytest.fixture(name="rabbitmq_container", scope="session")
def rabbitmq_container_fixture() -> Generator[RabbitMqContainer, None, None]:
    """Start a RabbitMQ container for Celery broker."""
    container = RabbitMqContainer(
        username=RABBITMQ_USER,
        password=RABBITMQ_PASSWORD,
    )

    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(RABBITMQ_INTERNAL_PORT)
        broker_url = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{host}:{port}//"
        environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}BROKER_URL"] = broker_url
        environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}APP_NAME"] = "spakky-celery-test"
        environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}TIMEZONE"] = "UTC"
        environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}RESULT_BACKEND"] = "rpc://"

        yield container

    for key in list(environ.keys()):
        if key.startswith(SPAKKY_CELERY_CONFIG_ENV_PREFIX):
            del environ[key]


@pytest.fixture(name="app_with_worker", scope="session")
def app_with_worker_fixture(
    rabbitmq_container: RabbitMqContainer,
) -> Generator[SpakkyApplication, Any, None]:
    """Create SpakkyApplication with Celery plugin and running worker."""

    @Pod()
    def get_celery(config: CeleryConfig) -> Celery:
        return Celery(
            main=config.app_name,
            broker=config.broker_url,
            backend=config.result_backend,
        )

    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.plugins.celery.PLUGIN_NAME})
        .add(get_celery)
        .scan(apps)
    )
    app.start()

    celery_instance = app.container.get(Celery)

    # Start worker in a thread (perform_ping_check=False because we register tasks dynamically)
    with start_worker(
        celery_instance,
        pool="solo",
        loglevel="INFO",
        perform_ping_check=False,
        shutdown_timeout=10.0,
    ):
        yield app

    app.stop()
    logger.removeHandler(console)


@pytest.fixture(autouse=True)
def clear_execution_record() -> Generator[None, Any, None]:
    """Clear execution record before each test for isolation."""
    execution_record.clear()
    yield
    execution_record.clear()
