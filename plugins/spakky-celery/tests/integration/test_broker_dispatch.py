"""Integration tests for Celery task dispatch through real broker.

These tests verify end-to-end task dispatch flow:
@task(background=True) method call → CeleryTaskDispatchAspect → RabbitMQ broker → Celery worker → Task execution

Uses testcontainers for RabbitMQ and celery.contrib.testing.worker for
running a real worker in a thread.
"""

from time import sleep, time

from spakky.core.application.application import SpakkyApplication

from tests.apps.dummy import (
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
# Scenario: Task dispatched through broker reaches worker (background=True)
# =============================================================================


def test_call_background_task_through_broker_expect_worker_processes_it(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task(background=True) 메서드 호출이 브로커를 통해 워커에서 처리된다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    email_handler = app_with_worker.container.get(EmailTaskHandler)

    # When: Calling a @task(background=True) method (aspect dispatches to broker)
    email_handler.send_email_async(
        to="user@example.com",
        subject="Integration Test",
        body="This message went through the broker!",
    )

    # Then: Worker picks up and executes the task
    wait_for_execution("send_email_async")
    assert execution_record.count("send_email_async") == 1
    recorded = execution_record.executions[0]
    assert recorded["to"] == "user@example.com"
    assert recorded["subject"] == "Integration Test"


def test_call_multiple_background_tasks_through_broker_expect_all_processed(
    app_with_worker: SpakkyApplication,
) -> None:
    """여러 @task(background=True) 메서드를 호출하면 워커가 모두 처리한다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    email_handler = app_with_worker.container.get(EmailTaskHandler)
    report_handler = app_with_worker.container.get(ReportTaskHandler)

    # When: Calling multiple @task(background=True) methods
    email_handler.send_email_async(
        to="first@example.com",
        subject="First",
        body="First email",
    )
    report_handler.generate_report_async(
        report_type="sales",
        params={"quarter": "Q1"},
    )
    email_handler.send_bulk_emails_async(
        recipients=["a@test.com", "b@test.com"],
        subject="Bulk",
    )

    # Then: All tasks are processed by the worker
    wait_for_execution("send_email_async", 1)
    wait_for_execution("generate_report_async", 1)
    wait_for_execution("send_bulk_emails_async", 1)
    assert execution_record.count() == 3


# =============================================================================
# Scenario: Immediate task execution (background=False)
# =============================================================================


def test_call_immediate_task_expect_executed_without_broker(
    app_with_worker: SpakkyApplication,
) -> None:
    """@task (background=False) 메서드는 브로커를 거치지 않고 즉시 실행된다."""
    # Given: A running Celery worker connected to RabbitMQ broker
    email_handler = app_with_worker.container.get(EmailTaskHandler)

    # When: Calling a @task (background=False) method
    email_handler.send_email(
        to="immediate@example.com",
        subject="Immediate",
        body="This runs immediately without broker",
    )

    # Then: Task is executed immediately (no waiting needed)
    assert execution_record.count("send_email") == 1
    recorded = execution_record.executions[0]
    assert recorded["to"] == "immediate@example.com"
