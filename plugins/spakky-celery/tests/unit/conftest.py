"""Unit test fixtures for spakky-celery plugin (eager mode)."""

import logging
from logging import Formatter, StreamHandler, getLogger
from os import environ
from typing import Any, Generator

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import spakky.plugins.celery
from spakky.plugins.celery.common.config import SPAKKY_CELERY_CONFIG_ENV_PREFIX
from tests import apps
from tests.apps.dummy import execution_record


@pytest.fixture(name="environment_variables", scope="module", autouse=True)
def environment_variables_fixture() -> Generator[None, Any, None]:
    """Set up environment variables for eager mode testing."""
    # Use in-memory broker for eager mode (no actual broker needed)
    environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}BROKER_URL"] = "memory://"
    environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}APP_NAME"] = "spakky-celery-test"
    environ[f"{SPAKKY_CELERY_CONFIG_ENV_PREFIX}TIMEZONE"] = "UTC"

    yield

    # Cleanup environment variables
    for key in list(environ.keys()):
        if key.startswith(SPAKKY_CELERY_CONFIG_ENV_PREFIX):
            del environ[key]


@pytest.fixture(name="app", scope="function")
def app_fixture() -> Generator[SpakkyApplication, Any, None]:
    """Create a SpakkyApplication with Celery plugin in eager mode."""
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.plugins.celery.PLUGIN_NAME})
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)
    execution_record.clear()
