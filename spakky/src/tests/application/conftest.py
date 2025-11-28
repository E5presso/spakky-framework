import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, Generator

import pytest

from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.aspects import LoggingAspect, TransactionalAspect
from tests.application import apps


@pytest.fixture(name="application", scope="function")
def application_fixture() -> Generator[SpakkyApplication, Any, None]:
    console = StreamHandler()
    console.setFormatter(Formatter("[%(asctime)s] [%(levelname)s] > %(message)s"))

    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console)

    app: SpakkyApplication = (
        SpakkyApplication(ApplicationContext())
        .add(TransactionalAspect)
        .add(LoggingAspect)
        .scan(apps)
        .load_plugins(include=set())
        .start()
    )
    yield app
    app.stop()
