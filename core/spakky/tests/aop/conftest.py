import logging
from logging import Formatter, Logger, StreamHandler, getLogger
from typing import Any, Generator

import pytest

from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects.logging import AsyncLoggingAspect, LoggingAspect
from spakky.core.common.importing import list_objects
from spakky.core.pod.annotations.pod import Pod
from tests.aop.apps import dummy


@pytest.fixture(name="application_context", scope="function")
def get_application_context_fixture() -> Generator[ApplicationContext, Any, None]:
    console = StreamHandler()
    console.setFormatter(Formatter("[%(asctime)s] [%(levelname)s] > %(message)s"))

    logger: Logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console)

    @Pod()
    def get_name() -> str:
        return "John"

    context: ApplicationContext = ApplicationContext()
    context.add(get_name)
    context.add(LoggingAspect)
    context.add(AsyncLoggingAspect)
    for obj in list_objects(dummy, Pod.exists):
        context.add(obj)
    context.start()

    yield context

    logger.handlers.clear()
