"""AOP aspects for intercepting @task method calls and dispatching them to Celery."""

from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.task_handler import TaskRoute

from celery import Celery
from spakky.plugins.celery.common.constants import CELERY_TASK_CONTEXT_KEY
from spakky.plugins.celery.common.task_result import CeleryTaskResult

logger = getLogger(__name__)


@Order(0)
@Aspect()
class CeleryTaskDispatchAspect(IAspect, IApplicationContextAware):
    """Intercepts synchronous @task method calls and dispatches them to Celery broker.

    All @task method calls from outside Celery context are dispatched via send_task().
    Inside a Celery worker, calls execute directly to avoid re-dispatch loops.
    """

    _celery: Celery
    _application_context: IApplicationContext

    def __init__(self, celery: Celery) -> None:
        """Initialize with the Celery application instance."""
        self._celery = celery

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Store the application context for checking worker context."""
        self._application_context = application_context

    @Around(lambda x: TaskRoute.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        if self._application_context.get_context_value(CELERY_TASK_CONTEXT_KEY):
            return joinpoint(*args, **kwargs)

        task_name: str = get_fully_qualified_name(joinpoint)
        async_result = self._celery.send_task(task_name, args=args, kwargs=kwargs)
        logger.debug("Dispatched task %s", task_name)
        return CeleryTaskResult(async_result)


@Order(0)
@AsyncAspect()
class AsyncCeleryTaskDispatchAspect(IAsyncAspect, IApplicationContextAware):
    """Intercepts asynchronous @task method calls and dispatches them to Celery broker.

    All @task method calls from outside Celery context are dispatched via send_task().
    Inside a Celery worker, calls execute directly to avoid re-dispatch loops.
    """

    _celery: Celery
    _application_context: IApplicationContext

    def __init__(self, celery: Celery) -> None:
        """Initialize with the Celery application instance."""
        self._celery = celery

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Store the application context for checking worker context."""
        self._application_context = application_context

    @Around(lambda x: TaskRoute.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        if self._application_context.get_context_value(CELERY_TASK_CONTEXT_KEY):
            return await joinpoint(*args, **kwargs)

        task_name: str = get_fully_qualified_name(joinpoint)
        async_result = self._celery.send_task(task_name, args=args, kwargs=kwargs)
        logger.debug("Dispatched task %s (async)", task_name)
        return CeleryTaskResult(async_result)
