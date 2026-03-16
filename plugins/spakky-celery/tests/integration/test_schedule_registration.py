"""Integration tests for scheduled task execution through real broker.

These tests verify that @schedule methods are dispatched through
RabbitMQ broker and actually executed by the Celery worker,
simulating what celery beat does via send_task().
"""

from time import sleep, time

from celery import Celery
from spakky.core.application.application import SpakkyApplication
from spakky.core.utils.inspection import get_fully_qualified_name

from tests.apps.dummy import HybridTaskHandler, ScheduledTaskHandler, execution_record

HEALTH_CHECK_TASK = get_fully_qualified_name(ScheduledTaskHandler.health_check)
DAILY_CLEANUP_TASK = get_fully_qualified_name(ScheduledTaskHandler.daily_cleanup)
TRIWEEKLY_REPORT_TASK = get_fully_qualified_name(ScheduledTaskHandler.triweekly_report)
HOURLY_SYNC_TASK = get_fully_qualified_name(HybridTaskHandler.hourly_sync)

POLL_INTERVAL = 0.05  # seconds between checks
MAX_WAIT_TIME = 10  # maximum seconds to wait


def wait_for_execution(task_name: str, expected_count: int = 1) -> None:
    """Poll until execution_record has expected count or timeout."""
    start = time()
    while execution_record.count(task_name) < expected_count:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for {task_name} to execute {expected_count} time(s). "
                f"Current count: {execution_record.count(task_name)}"
            )
        sleep(POLL_INTERVAL)


# =============================================================================
# Scenario: Scheduled tasks dispatched through broker reach worker
# =============================================================================


def test_interval_schedule_task_dispatched_through_broker_expect_worker_executes(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(interval=...) 태스크를 send_task로 디스패치하면 워커가 실행한다."""
    # Given: A running Celery worker with scheduled tasks registered
    celery = app_with_worker.container.get(Celery)

    # When: Simulating what celery beat does — dispatch via send_task
    celery.send_task(HEALTH_CHECK_TASK)

    # Then: Worker picks up and executes the scheduled task
    wait_for_execution("health_check")
    assert execution_record.count("health_check") == 1


def test_at_schedule_task_dispatched_through_broker_expect_worker_executes(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(at=...) 태스크를 send_task로 디스패치하면 워커가 실행한다."""
    celery = app_with_worker.container.get(Celery)

    celery.send_task(DAILY_CLEANUP_TASK)

    wait_for_execution("daily_cleanup")
    assert execution_record.count("daily_cleanup") == 1


def test_crontab_schedule_task_dispatched_through_broker_expect_worker_executes(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule(crontab=...) 태스크를 send_task로 디스패치하면 워커가 실행한다."""
    celery = app_with_worker.container.get(Celery)

    celery.send_task(TRIWEEKLY_REPORT_TASK)

    wait_for_execution("triweekly_report")
    assert execution_record.count("triweekly_report") == 1


def test_all_scheduled_tasks_dispatched_through_broker_expect_all_executed(
    app_with_worker: SpakkyApplication,
) -> None:
    """모든 @schedule 태스크를 동시에 디스패치하면 워커가 전부 실행한다."""
    celery = app_with_worker.container.get(Celery)

    celery.send_task(HEALTH_CHECK_TASK)
    celery.send_task(DAILY_CLEANUP_TASK)
    celery.send_task(TRIWEEKLY_REPORT_TASK)

    wait_for_execution("health_check")
    wait_for_execution("daily_cleanup")
    wait_for_execution("triweekly_report")
    assert execution_record.count() == 3


# =============================================================================
# Scenario: Hybrid task (@task + @schedule) schedule registration
# =============================================================================


def test_hybrid_task_registered_in_beat_schedule(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task + @schedule 메서드가 beat_schedule에 등록된다."""
    celery = app_with_worker.container.get(Celery)

    # Then: Hybrid task is registered in beat_schedule
    assert HOURLY_SYNC_TASK in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[HOURLY_SYNC_TASK]
    assert entry["task"] == HOURLY_SYNC_TASK


def test_hybrid_task_dispatched_via_send_task_expect_worker_executes(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task + @schedule 메서드를 send_task로 디스패치하면 워커가 실행한다."""
    celery = app_with_worker.container.get(Celery)

    # When: Simulating what celery beat does — dispatch via send_task
    celery.send_task(HOURLY_SYNC_TASK)

    # Then: Worker picks up and executes the task
    wait_for_execution("hourly_sync")
    assert execution_record.count("hourly_sync") == 1


# =============================================================================
# Scenario: Direct invocation of schedule-only methods
# =============================================================================


def test_schedule_only_method_direct_call_executes_locally_not_via_worker(
    app_with_worker: SpakkyApplication,
) -> None:
    """@schedule만 있는 메서드를 직접 호출하면 워커를 거치지 않고 로컬에서 즉시 실행된다."""
    # Given: A running Celery worker with scheduled tasks
    handler = app_with_worker.container.get(ScheduledTaskHandler)
    initial_count = execution_record.count("health_check")

    # When: Directly calling a @schedule-only method (no @task decorator)
    handler.health_check()

    # Then: Executes immediately and synchronously — no polling required
    # If it went through worker, we'd need wait_for_execution()
    assert execution_record.count("health_check") == initial_count + 1
