"""AOP aspects for intercepting @task method calls and dispatching them to Celery."""

from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.task.stereotype.task_handler import TaskRoute

from celery import current_task
from spakky.plugins.celery.app import CeleryApp

logger = getLogger(__name__)


@Order(0)
@Aspect()
class CeleryTaskDispatchAspect(IAspect):
    """Intercepts synchronous @task method calls and dispatches them to Celery.

    Behavior depends on TaskRoute.background:
    - background=False (default): execute via apply() with Celery's retry/error handling
    - background=True: dispatch to broker via send_task()
    """

    _celery_app: CeleryApp

    def __init__(self, celery_app: CeleryApp) -> None:
        self._celery_app = celery_app

    @Around(lambda x: TaskRoute.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        # If we're inside a Celery task context, execute directly (no re-dispatch)
        # current_task is a LocalProxy, so use boolean evaluation
        if current_task:
            return joinpoint(*args, **kwargs)

        route: TaskRoute = TaskRoute.get(joinpoint)
        task_name: str = joinpoint.__name__

        if not route.background:
            celery_task = self._celery_app.task_routes[task_name]
            result = celery_task.apply(args=args, kwargs=kwargs)
            return result.get()

        self._celery_app.celery.send_task(task_name, args=args, kwargs=kwargs)
        logger.debug("Dispatched task %s", task_name)


@Order(0)
@AsyncAspect()
class AsyncCeleryTaskDispatchAspect(IAsyncAspect):
    """Intercepts asynchronous @task method calls and dispatches them to Celery.

    Behavior depends on TaskRoute.background:
    - background=False (default): execute via apply() with Celery's retry/error handling
    - background=True: dispatch to broker via send_task()
    """

    _celery_app: CeleryApp

    def __init__(self, celery_app: CeleryApp) -> None:
        self._celery_app = celery_app

    @Around(lambda x: TaskRoute.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        # If we're inside a Celery task context, execute directly (no re-dispatch)
        # current_task is a LocalProxy, so use boolean evaluation
        if current_task:
            return await joinpoint(*args, **kwargs)

        route: TaskRoute = TaskRoute.get(joinpoint)
        task_name: str = joinpoint.__name__

        if not route.background:
            celery_task = self._celery_app.task_routes[task_name]
            result = celery_task.apply(args=args, kwargs=kwargs)
            return result.get()

        self._celery_app.celery.send_task(task_name, args=args, kwargs=kwargs)
        logger.debug("Dispatched task %s (async)", task_name)
