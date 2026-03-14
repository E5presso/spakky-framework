"""Unit tests for ScheduleRoute and @schedule decorator."""

from datetime import time, timedelta

import pytest

from spakky.task.error import InvalidScheduleSpecificationError
from spakky.task.stereotype.crontab import Crontab, Weekday
from spakky.task.stereotype.schedule import ScheduleRoute, schedule
from spakky.task.stereotype.task_handler import TaskHandler


def test_schedule_with_interval_expect_annotation_applied() -> None:
    """@schedule(interval=...)가 ScheduleRoute를 정상 적용하는지 검증한다."""

    @TaskHandler()
    class Handler:
        @schedule(interval=timedelta(minutes=30))
        def health_check(self) -> None:
            pass

    handler = Handler()
    assert ScheduleRoute.exists(handler.health_check) is True
    route = ScheduleRoute.get(handler.health_check)
    assert route.interval == timedelta(minutes=30)
    assert route.at is None
    assert route.crontab is None


def test_schedule_with_at_expect_annotation_applied() -> None:
    """@schedule(at=...)가 ScheduleRoute를 정상 적용하는지 검증한다."""

    @TaskHandler()
    class Handler:
        @schedule(at=time(3, 0))
        def daily_cleanup(self) -> None:
            pass

    handler = Handler()
    route = ScheduleRoute.get(handler.daily_cleanup)
    assert route.at == time(3, 0)
    assert route.interval is None
    assert route.crontab is None


def test_schedule_with_crontab_expect_annotation_applied() -> None:
    """@schedule(crontab=...)가 ScheduleRoute를 정상 적용하는지 검증한다."""
    cron = Crontab(hour=9, weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY))

    @TaskHandler()
    class Handler:
        @schedule(crontab=cron)
        def triweekly_report(self) -> None:
            pass

    handler = Handler()
    route = ScheduleRoute.get(handler.triweekly_report)
    assert route.crontab == cron
    assert route.interval is None
    assert route.at is None


def test_schedule_no_option_expect_raises_error() -> None:
    """@schedule() 옵션 없이 호출하면 InvalidScheduleSpecificationError가 발생하는지 검증한다."""
    with pytest.raises(InvalidScheduleSpecificationError):
        schedule()


def test_schedule_multiple_options_expect_raises_error() -> None:
    """@schedule()에 여러 옵션을 동시에 전달하면 InvalidScheduleSpecificationError가 발생하는지 검증한다."""
    with pytest.raises(InvalidScheduleSpecificationError):
        schedule(interval=timedelta(minutes=5), at=time(3, 0))


def test_schedule_route_get_or_none_returns_none_for_unannotated() -> None:
    """ScheduleRoute.get_or_none()이 어노테이션 없는 메서드에 None을 반환하는지 검증한다."""

    @TaskHandler()
    class Handler:
        def regular_method(self) -> None:
            pass

    handler = Handler()
    assert ScheduleRoute.get_or_none(handler.regular_method) is None


def test_task_and_schedule_are_independent_annotations() -> None:
    """@task와 @schedule이 서로 다른 독립 어노테이션인지 검증한다."""
    from spakky.task.stereotype.task_handler import TaskRoute, task

    @TaskHandler()
    class Handler:
        @task
        def on_demand(self) -> None:
            pass

        @schedule(interval=timedelta(hours=1))
        def periodic(self) -> None:
            pass

    handler = Handler()
    assert TaskRoute.exists(handler.on_demand) is True
    assert ScheduleRoute.exists(handler.on_demand) is False
    assert ScheduleRoute.exists(handler.periodic) is True
    assert TaskRoute.exists(handler.periodic) is False
