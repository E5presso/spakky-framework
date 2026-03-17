"""Integration tests for Celery task dispatch through real broker.

These tests verify end-to-end task dispatch flow:
@task method call → CeleryTaskDispatchAspect → RabbitMQ broker → Celery worker → Task execution

Uses testcontainers for RabbitMQ and celery.contrib.testing.worker for
running a real worker in a thread.
"""

from time import sleep, time

from spakky.core.application.application import SpakkyApplication
from spakky.task.interfaces.task_result import AbstractTaskResult

from tests.apps.dummy import (
    AsyncNotificationHandler,
    AsyncResultTaskHandler,
    EmailTaskHandler,
    ReportTaskHandler,
    execution_record,
)

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
# Scenario: Task dispatched through broker reaches worker
# =============================================================================


def test_call_task_through_broker_expect_worker_processes_it(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task 메서드 호출이 브로커를 통해 워커에서 처리된다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    email_handler = app_with_worker.container.get(EmailTaskHandler)

    # When: Calling a @task method (aspect dispatches to broker)
    email_handler.send_email(
        to="user@example.com",
        subject="Integration Test",
        body="This message went through the broker!",
    )

    # Then: Worker picks up and executes the task
    wait_for_execution("send_email")
    assert execution_record.count("send_email") == 1
    recorded = execution_record.executions[0]
    assert recorded["to"] == "user@example.com"
    assert recorded["subject"] == "Integration Test"


def test_call_multiple_tasks_through_broker_expect_all_processed(
    app_with_worker: SpakkyApplication,
) -> None:
    """여러 @task 메서드를 호출하면 워커가 모두 처리한다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    email_handler = app_with_worker.container.get(EmailTaskHandler)
    report_handler = app_with_worker.container.get(ReportTaskHandler)

    # When: Calling multiple @task methods
    email_handler.send_email(
        to="first@example.com",
        subject="First",
        body="First email",
    )
    report_handler.generate_report(
        report_type="sales",
        params={"quarter": "Q1"},
    )
    email_handler.send_bulk_emails(
        recipients=["a@test.com", "b@test.com"],
        subject="Bulk",
    )

    # Then: All tasks are processed by the worker
    wait_for_execution("send_email", 1)
    wait_for_execution("generate_report", 1)
    wait_for_execution("send_bulk_emails", 1)
    assert execution_record.count() == 3


# =============================================================================
# Scenario: Async task handlers (coroutine methods)
# =============================================================================


async def test_call_async_task_through_broker_expect_worker_processes_it(
    app_with_worker: SpakkyApplication,
) -> None:
    """async @task 메서드 호출이 브로커를 통해 워커에서 처리된다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    notification_handler = app_with_worker.container.get(AsyncNotificationHandler)

    # When: Calling an async @task method
    result = await notification_handler.send_notification(
        user_id="user-123",
        message="Async notification through broker",
    )
    # Verify we got a task result (dispatched to broker)
    assert result is not None

    # Then: Worker picks up and executes the async task
    wait_for_execution("send_notification")
    assert execution_record.count("send_notification") == 1
    recorded = execution_record.executions[0]
    assert recorded["user_id"] == "user-123"
    assert recorded["message"] == "Async notification through broker"


# =============================================================================
# Scenario: Hybrid task (both @task and @schedule)
# =============================================================================


def test_hybrid_task_can_be_dispatched_manually_expect_worker_processes_it(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task + @schedule 메서드를 수동으로 호출하면 워커가 처리한다."""
    # Given: A running Celery worker with hybrid task registered
    from tests.apps.dummy import HybridTaskHandler

    hybrid_handler = app_with_worker.container.get(HybridTaskHandler)

    # When: Calling the hybrid method manually (via @task aspect dispatch)
    hybrid_handler.hourly_sync()

    # Then: Worker picks up and executes the task
    wait_for_execution("hourly_sync")
    assert execution_record.count("hourly_sync") == 1


# =============================================================================
# Scenario: Async result retrieval via get_async()
# =============================================================================


async def test_get_async_retrieves_async_task_return_value_from_broker(
    app_with_worker: SpakkyApplication,
) -> None:
    """get_async() returns the value from a sync @task executed through the broker without blocking the event loop."""
    # Given: A running Celery worker connected to RabbitMQ broker with result backend
    handler = app_with_worker.container.get(AsyncResultTaskHandler)

    # When: Dispatching a sync @task that returns a value (dispatch itself is synchronous)
    result = handler.compute(value=21)
    assert isinstance(result, AbstractTaskResult)

    # Then: get_async() retrieves the task's return value without blocking the event loop
    value = await result.get_async()
    assert value == 42
    assert execution_record.count("compute") == 1
