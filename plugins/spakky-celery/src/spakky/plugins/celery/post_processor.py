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
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.crontab import Crontab, Month, Weekday
from spakky.task.stereotype.schedule import ScheduleRoute
from spakky.task.stereotype.task_handler import TaskHandler, TaskRoute

from celery import Celery
from celery.schedules import crontab as celery_crontab
from celery.schedules import schedule as celery_schedule
from spakky.plugins.celery.common.constants import CELERY_TASK_CONTEXT_KEY
from spakky.plugins.celery.error import InvalidScheduleRouteError

logger = getLogger(__name__)


@Order(0)
@Pod()
class CeleryPostProcessor(IPostProcessor, IApplicationContextAware):
    """Post-processor that registers TaskHandler-annotated Pods as Celery tasks."""

    __application_context: IApplicationContext

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Store the application context for resolving handlers at runtime."""
        self.__application_context = application_context

    def _create_sync_endpoint(
        self,
        handler_type: type[object],
        method: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Create a sync endpoint that resolves handler from container."""

        @wraps(method)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            self.__application_context.clear_context()
            self.__application_context.set_context_value(CELERY_TASK_CONTEXT_KEY, True)
            handler_instance = self.__application_context.get(handler_type)
            bound_method = method.__get__(handler_instance, handler_type)
            return bound_method(*args, **kwargs)

        return endpoint

    def _create_async_endpoint(
        self,
        handler_type: type[object],
        method: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Create an endpoint for async methods.

        Wraps the async method to run via asyncio.run() in Celery worker process.
        For tests with existing event loops, use nest_asyncio in conftest.py.
        """

        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async wrapper that sets context and invokes handler method."""
            self.__application_context.clear_context()
            self.__application_context.set_context_value(CELERY_TASK_CONTEXT_KEY, True)
            handler_instance = self.__application_context.get(handler_type)
            bound_method = method.__get__(handler_instance, handler_type)
            return await bound_method(*args, **kwargs)

        @wraps(method)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            return asyncio.run(_async_wrapper(*args, **kwargs))

        return endpoint

    @staticmethod
    def _to_celery_schedule(route: ScheduleRoute) -> celery_schedule | celery_crontab:
        """Convert a ScheduleRoute to a Celery schedule object."""
        if route.interval is not None:
            return celery_schedule(run_every=route.interval)
        if route.at is not None:
            return celery_crontab(hour=route.at.hour, minute=route.at.minute)
        if route.crontab is not None:
            return CeleryPostProcessor._crontab_to_celery(route.crontab)
        raise InvalidScheduleRouteError()  # pragma: no cover - ScheduleRoute.__post_init__이 사전 검증

    @staticmethod
    def _crontab_to_celery(cron: Crontab) -> celery_crontab:
        """Convert a Crontab value object to Celery crontab."""

        def _to_str(
            value: int | Month | Weekday | tuple[int | Month | Weekday, ...] | None,
        ) -> str:
            if value is None:
                return "*"
            values = value if isinstance(value, tuple) else (value,)
            return ",".join(str(int(v)) for v in values)

        return celery_crontab(
            month_of_year=_to_str(cron.month),
            day_of_month=_to_str(cron.day),
            day_of_week=_to_str(cron.weekday),
            hour=str(cron.hour),
            minute=str(cron.minute),
        )

    def _register_method(
        self,
        celery: Celery,
        pod_type: type[object],
        method: Callable[..., Any],
    ) -> str:
        """Register a single method as a Celery task. Returns the task name."""
        if iscoroutinefunction(method):
            endpoint = self._create_async_endpoint(pod_type, method)
        else:
            endpoint = self._create_sync_endpoint(pod_type, method)

        task_name = get_fully_qualified_name(method)
        celery.task(name=task_name)(endpoint)
        return task_name

    def post_process(self, pod: object) -> object:
        """Register TaskHandler methods as Celery tasks and beat schedules."""
        if not TaskHandler.exists(pod):
            return pod

        celery: Celery = self.__application_context.get(Celery)
        pod_type = TaskHandler.get(pod).type_

        for _, method in getmembers(pod_type, isfunction):
            has_task = TaskRoute.get_or_none(method) is not None
            schedule_route = ScheduleRoute.get_or_none(method)
            has_schedule = schedule_route is not None

            if not has_task and not has_schedule:
                continue

            task_name = self._register_method(celery, pod_type, method)

            if has_schedule:
                assert schedule_route is not None
                celery.conf.beat_schedule[task_name] = {
                    "task": task_name,
                    "schedule": self._to_celery_schedule(schedule_route),
                }
                logger.debug(
                    "Registered beat schedule '%s' from handler '%s'",
                    task_name,
                    pod_type.__name__,
                )
            else:
                logger.debug(
                    "Registered task '%s' from handler '%s'",
                    task_name,
                    pod_type.__name__,
                )

        return pod
