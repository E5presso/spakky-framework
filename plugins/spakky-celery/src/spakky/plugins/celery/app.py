"""Celery application wrapper."""

from logging import getLogger
from typing import Callable, Final, cast

from spakky.core.pod.annotations.pod import Pod

from celery import Celery, Task
from spakky.plugins.celery.common.config import CeleryConfig

logger = getLogger(__name__)


@Pod()
class CeleryApp:
    """Pod that holds the Celery instance and manages task routes."""

    _config: Final[CeleryConfig]
    _celery: Final[Celery]
    _task_routes: dict[str, Task]

    def __init__(self, config: CeleryConfig) -> None:
        self._config = config
        self._celery = Celery(
            main=config.app_name,
            broker=config.broker_url,
            backend=config.result_backend,
        )
        self._celery.conf.update(
            task_serializer=config.task_serializer.value,
            accept_content=[s.value for s in config.accept_content],
            result_serializer=config.result_serializer.value,
            timezone=config.timezone,
            enable_utc=config.enable_utc,
        )
        self._task_routes = {}

    @property
    def celery(self) -> Celery:
        return self._celery

    @property
    def task_routes(self) -> dict[str, Task]:
        return self._task_routes

    def register_task(
        self,
        name: str,
        handler: Callable[..., object],
    ) -> None:
        registered = cast(Task, self._celery.task(name=name)(handler))
        self._task_routes[name] = registered
        logger.info("Registered celery task: %s", name)
