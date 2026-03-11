"""Post-processor for registering TaskHandler methods as Celery tasks."""

from inspect import getmembers
from logging import getLogger

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
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

    def post_process(self, pod: object) -> object:
        if not TaskHandler.exists(pod):
            return pod

        celery_app = self.__container.get(CeleryApp)
        pod_type = type(pod)

        for name, method in getmembers(pod, callable):
            route: TaskRoute | None = TaskRoute.get_or_none(method)
            if route is None:
                continue

            celery_app.register_task(name, method)
            logger.debug(
                "Registered task '%s' from handler '%s'",
                name,
                pod_type.__name__,
            )

        return pod
