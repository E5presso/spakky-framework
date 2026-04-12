"""Task handler registration post-processor."""

from inspect import getmembers, ismethod
from logging import getLogger

from spakky.core.common.types import Func
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from typing_extensions import override

from spakky.task.stereotype.task_handler import TaskHandler, TaskRoute

logger = getLogger(__name__)


@Pod()
class TaskRegistrationPostProcessor(IPostProcessor):
    """Post-processor that scans @TaskHandler pods for @task methods.

    This post-processor collects all task routes from TaskHandler pods
    and makes them available for task queue implementations to register.
    """

    _task_routes: dict[Func, TaskRoute]

    def __init__(self) -> None:
        self._task_routes = {}

    @override
    def post_process(self, pod: object) -> object:
        """Scan pod for @task methods and register their routes.

        Args:
            pod: The pod instance to process.

        Returns:
            The unmodified pod instance.
        """
        pod_type = type(pod)

        if not TaskHandler.exists(pod_type):
            return pod

        for name, method in getmembers(pod, predicate=ismethod):
            route = TaskRoute.get_or_none(method)
            if route is None:
                continue

            self._task_routes[method] = route
            logger.debug(f"Registered task {pod_type.__name__}.{name}")

        return pod

    def get_task_routes(self) -> dict[Func, TaskRoute]:
        """Get all registered task routes.

        Returns:
            Dictionary mapping task methods to their routes.
        """
        return self._task_routes.copy()
