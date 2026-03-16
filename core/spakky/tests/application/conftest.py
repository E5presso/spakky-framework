import logging
from logging import Formatter, StreamHandler, getLogger
from typing import Any, Generator

import pytest

from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from tests.application import apps


@Aspect()
class DummyAspect(IAspect): ...


@pytest.fixture(name="application", scope="function")
def application_fixture() -> Generator[SpakkyApplication, Any, None]:
    console = StreamHandler()
    console.setFormatter(Formatter("[%(asctime)s] [%(levelname)s] > %(message)s"))

    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console)

    app: SpakkyApplication = (
        SpakkyApplication(ApplicationContext())
        .add(DummyAspect)
        .scan(apps)
        .load_plugins(include=set())
        .start()
    )
    yield app
    app.stop()
