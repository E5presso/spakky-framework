"""Schedule stereotype for periodic task execution.

Provides @schedule decorator to mark TaskHandler methods for
periodic execution (interval, daily, or crontab-based).
"""

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Callable, ParamSpec, TypeVar, cast

from spakky.core.common.annotation import FunctionAnnotation

from spakky.task.error import InvalidScheduleSpecificationError
from spakky.task.stereotype.crontab import Crontab

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class ScheduleRoute(FunctionAnnotation):
    """Annotation for marking methods as periodically scheduled tasks.

    Exactly one of ``interval``, ``at``, or ``crontab`` must be provided.
    """

    interval: timedelta | None = None
    """Fixed interval between executions."""

    at: time | None = None
    """Daily execution at a specific time."""

    crontab: Crontab | None = None
    """Cron-like schedule specification."""

    def __post_init__(self) -> None:
        specified = sum(x is not None for x in (self.interval, self.at, self.crontab))
        if specified != 1:
            raise InvalidScheduleSpecificationError()


def schedule(
    *,
    interval: timedelta | None = None,
    at: time | None = None,
    crontab: Crontab | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for marking methods as periodically scheduled tasks.

    Exactly one of ``interval``, ``at``, or ``crontab`` must be specified.

    Example:
        @TaskHandler()
        class MaintenanceHandler:
            @schedule(interval=timedelta(minutes=30))
            def health_check(self) -> None:
                ...

            @schedule(at=time(3, 0))
            def daily_cleanup(self) -> None:
                ...

            @schedule(crontab=Crontab(hour=9, weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)))
            def triweekly_report(self) -> None:
                ...

    Args:
        interval: Fixed interval between executions.
        at: Daily execution at a specific time.
        crontab: Cron-like schedule specification.

    Returns:
        A decorator that annotates the method with ScheduleRoute.
    """
    route = ScheduleRoute(interval=interval, at=at, crontab=crontab)
    return cast(Callable[[Callable[P, T]], Callable[P, T]], route)
