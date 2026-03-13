"""AOP aspects for intercepting @task method calls and dispatching them to Celery."""

from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.task_handler import TaskRoute

from celery import current_task
from spakky.plugins.celery.app import CeleryApp
from spakky.plugins.celery.common.task_result import CeleryTaskResult
from spakky.plugins.celery.post_processor import celery_task_context

logger = getLogger(__name__)


def _is_inside_celery_task() -> bool:
    """Check if we're currently inside a Celery task execution context.

    This checks both the Celery current_task proxy and the explicit context
    variable set by post_processor (for async tasks running in ThreadPoolExecutor).
    """
    return bool(current_task) or celery_task_context.get()


@Order(0)
@Aspect()
class CeleryTaskDispatchAspect(IAspect):
    """Intercepts synchronous @task method calls and dispatches them to Celery.

    Behavior depends on TaskRoute.background:
    - background=False (default): execute via apply() with Celery's retry/error handling
    - background=True: dispatch to broker via send_task() and return AsyncResult
    """

    _celery_app: CeleryApp

    def __init__(self, celery_app: CeleryApp) -> None:
        self._celery_app = celery_app

    @Around(lambda x: TaskRoute.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        # If we're inside a Celery task context, execute directly (no re-dispatch)
        if _is_inside_celery_task():
            return joinpoint(*args, **kwargs)

        route: TaskRoute = TaskRoute.get(joinpoint)
        task_name: str = get_fully_qualified_name(joinpoint)

        if not route.background:
            celery_task = self._celery_app.task_routes[task_name]
            result = celery_task.apply(args=args, kwargs=kwargs)
            return result.get()

        async_result = self._celery_app.celery.send_task(
            task_name, args=args, kwargs=kwargs
        )
        logger.debug("Dispatched task %s", task_name)
        return CeleryTaskResult(async_result)


@Order(0)
@AsyncAspect()
class AsyncCeleryTaskDispatchAspect(IAsyncAspect):
    """Intercepts asynchronous @task method calls and dispatches them to Celery.

    Behavior depends on TaskRoute.background:
    - background=False (default): execute via apply() with Celery's retry/error handling
    - background=True: dispatch to broker via send_task() and return AsyncResult
    """

    _celery_app: CeleryApp

    def __init__(self, celery_app: CeleryApp) -> None:
        self._celery_app = celery_app

    @Around(lambda x: TaskRoute.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        # If we're inside a Celery task context, execute directly (no re-dispatch)
        if _is_inside_celery_task():
            return await joinpoint(*args, **kwargs)

        route: TaskRoute = TaskRoute.get(joinpoint)
        task_name: str = get_fully_qualified_name(joinpoint)

        if not route.background:
            celery_task = self._celery_app.task_routes[task_name]
            result = celery_task.apply(args=args, kwargs=kwargs)
            return result.get()

        async_result = self._celery_app.celery.send_task(
            task_name, args=args, kwargs=kwargs
        )
        logger.debug("Dispatched task %s (async)", task_name)
        return CeleryTaskResult(async_result)
