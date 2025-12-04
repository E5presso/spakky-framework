import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, AsyncGenerator, Generator

import pytest
import spakky.plugins.fastapi
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects import AsyncLoggingAspect, LoggingAspect
from spakky.core.pod.annotations.pod import Pod

from fastapi import FastAPI
from tests import apps


@pytest.fixture(name="name", scope="package")
def get_name_fixture() -> Generator[str, Any, None]:
    name: str = "John"
    yield name


@pytest.mark.asyncio
@pytest.fixture(name="app", scope="function")
async def get_app_fixture(name: str) -> AsyncGenerator[SpakkyApplication, Any]:
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    @Pod(name="key")
    def get_name() -> str:
        return name

    @Pod(name="api")
    def get_api() -> FastAPI:
        return FastAPI(debug=True)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.plugins.fastapi.PLUGIN_NAME})
        .add(AsyncLoggingAspect)
        .add(LoggingAspect)
        .scan(apps)
        .add(get_name)
        .add(get_api)
    )
    app.start()

    yield app

    logger.removeHandler(console)


@pytest.mark.asyncio
@pytest.fixture(name="api", scope="function")
async def get_api_fixture(app: SpakkyApplication) -> AsyncGenerator[FastAPI, Any]:
    yield app.container.get(type_=FastAPI)
