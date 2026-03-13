"""Post-processor for registering TaskHandler methods as Celery tasks."""

import asyncio
from functools import wraps
from inspect import getmembers, iscoroutinefunction, isfunction
from logging import getLogger
from typing import Any, Callable

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.task_handler import TaskHandler, TaskRoute

from spakky.plugins.celery.app import CeleryApp

logger = getLogger(__name__)


@Order(0)
@Pod()
class CeleryPostProcessor(IPostProcessor, IContainerAware, IApplicationContextAware):
    """Post-processor that registers TaskHandler-annotated Pods as Celery tasks."""

    __container: IContainer
    __application_context: IApplicationContext

    def set_container(self, container: IContainer) -> None:
        self.__container = container

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    def _create_sync_endpoint(
        self,
        method_name: str,
        handler_type: type[object],
        method: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Create a sync endpoint that resolves handler from container."""

        @wraps(method)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            self.__application_context.clear_context()
            handler_instance = self.__container.get(handler_type)
            method_to_call = getattr(handler_instance, method_name)
            return method_to_call(*args, **kwargs)

        return endpoint

    def _create_async_endpoint(
        self,
        method_name: str,
        handler_type: type[object],
        method: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Create an endpoint for async methods that runs in event loop."""

        @wraps(method)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            self.__application_context.clear_context()
            handler_instance = self.__container.get(handler_type)
            method_to_call = getattr(handler_instance, method_name)
            return asyncio.run(method_to_call(*args, **kwargs))

        return endpoint

    def post_process(self, pod: object) -> object:
        if not TaskHandler.exists(pod):
            return pod

        celery_app = self.__container.get(CeleryApp)
        pod_type = TaskHandler.get(pod).type_

        for name, method in getmembers(pod_type, isfunction):
            route: TaskRoute | None = TaskRoute.get_or_none(method)
            if route is None:
                continue

            if iscoroutinefunction(method):
                endpoint = self._create_async_endpoint(name, pod_type, method)
            else:
                endpoint = self._create_sync_endpoint(name, pod_type, method)

            task_name = get_fully_qualified_name(method)
            celery_app.register_task(task_name, endpoint)
            logger.debug(
                "Registered task '%s' from handler '%s'",
                task_name,
                pod_type.__name__,
            )

        return pod
