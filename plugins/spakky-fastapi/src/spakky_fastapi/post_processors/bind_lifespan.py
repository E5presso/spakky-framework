"""Post-processor for binding FastAPI lifespan to ApplicationContext lifecycle.

Automatically wraps FastAPI lifespan to ensure ApplicationContext.stop()
is called when FastAPI shuts down, enabling graceful shutdown of
background services like RabbitMQ consumers.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Mapping

from fastapi import FastAPI
from spakky.pod.annotations.order import Order
from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.pod.interfaces.post_processor import IPostProcessor


@Order(0)
@Pod()
class BindLifespanPostProcessor(IPostProcessor, IApplicationContextAware):
    """Post-processor that binds FastAPI lifespan to ApplicationContext lifecycle.

    Wraps the FastAPI lifespan handler to ensure ApplicationContext.stop() is
    called when FastAPI shuts down. This enables graceful shutdown of all
    background services registered with the application context.

    User-defined lifespan handlers are preserved and executed normally.
    """

    __application_context: IApplicationContext

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context for lifecycle binding.

        Args:
            application_context: The application context to stop on shutdown.
        """
        self.__application_context = application_context

    def post_process(self, pod: object) -> object:
        """Wrap FastAPI lifespan to bind ApplicationContext lifecycle.

        Args:
            pod: The Pod to process.

        Returns:
            The Pod with lifespan wrapped if it's a FastAPI instance.
        """
        if not isinstance(pod, FastAPI):
            return pod

        original_lifespan = pod.router.lifespan_context
        application_context = self.__application_context

        @asynccontextmanager
        async def wrapped_lifespan(app: FastAPI) -> AsyncIterator[Mapping[str, Any]]:
            try:
                async with original_lifespan(app) as state:
                    yield state if state is not None else {}
            finally:
                application_context.stop()

        pod.router.lifespan_context = wrapped_lifespan
        return pod
