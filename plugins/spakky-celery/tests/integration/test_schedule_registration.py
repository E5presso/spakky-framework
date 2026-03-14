"""Integration tests for schedule registration through real broker.

These tests verify that @schedule methods (interval, at, crontab)
are correctly registered in Celery's beat_schedule when using a
real RabbitMQ broker.
"""

from celery import Celery
from celery.schedules import crontab as celery_crontab
from celery.schedules import schedule as celery_schedule
from spakky.core.application.application import SpakkyApplication

SCHEDULED_PREFIX = "tests.apps.dummy.ScheduledTaskHandler"


def test_interval_schedule_registered_in_beat_schedule(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(interval=...) 메서드가 브로커 환경에서 beat_schedule에 등록되는지 검증한다."""
    celery = app_with_worker.container.get(Celery)
    task_name = f"{SCHEDULED_PREFIX}.health_check"

    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert entry["task"] == task_name
    assert isinstance(entry["schedule"], celery_schedule)


def test_at_schedule_registered_as_crontab_in_beat_schedule(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(at=...) 메서드가 브로커 환경에서 celery crontab으로 beat_schedule에 등록되는지 검증한다."""
    celery = app_with_worker.container.get(Celery)
    task_name = f"{SCHEDULED_PREFIX}.daily_cleanup"

    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert entry["task"] == task_name
    assert isinstance(entry["schedule"], celery_crontab)


def test_crontab_schedule_registered_in_beat_schedule(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(crontab=...) 메서드가 브로커 환경에서 beat_schedule에 등록되는지 검증한다."""
    celery = app_with_worker.container.get(Celery)
    task_name = f"{SCHEDULED_PREFIX}.triweekly_report"

    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert entry["task"] == task_name
    assert isinstance(entry["schedule"], celery_crontab)


def test_crontab_schedule_has_correct_values(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(crontab=...) 등록된 엔트리가 올바른 cron 값을 가지는지 검증한다."""
    celery = app_with_worker.container.get(Celery)
    task_name = f"{SCHEDULED_PREFIX}.triweekly_report"
    entry = celery.conf.beat_schedule[task_name]
    cron = entry["schedule"]

    assert isinstance(cron, celery_crontab)
    expected = celery_crontab(minute="0", hour="9", day_of_week="0,2,4")
    assert cron == expected


def test_all_scheduled_tasks_also_registered_as_celery_tasks(
    app_with_worker: SpakkyApplication,
) -> None:
    """모든 @schedule 메서드가 Celery task로도 등록되는지 검증한다."""
    celery = app_with_worker.container.get(Celery)

    assert f"{SCHEDULED_PREFIX}.health_check" in celery.tasks
    assert f"{SCHEDULED_PREFIX}.daily_cleanup" in celery.tasks
    assert f"{SCHEDULED_PREFIX}.triweekly_report" in celery.tasks
