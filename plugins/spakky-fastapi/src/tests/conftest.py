import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.pod.annotations.pod import Pod

import spakky_fastapi
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
        SpakkyApplication(ApplicationContext(logger))
        .load_plugins(include={spakky_fastapi.PLUGIN_NAME})
        .enable_async_logging()
        .enable_logging()
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
