"""Unit tests for Celery task dispatch with background=False (default).

With background=False, the CeleryTaskDispatchAspect executes tasks immediately
via joinpoint() instead of dispatching to the broker.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.celery.app import CeleryApp
from tests.apps.dummy import (
    EmailTaskHandler,
    ReportTaskHandler,
    execution_record,
)

# =============================================================================
# Scenario: Task Registration
# =============================================================================


def test_task_handlers_registered_on_app_start_expect_tasks_in_celery(
    app: SpakkyApplication,
) -> None:
    """TaskHandler로 어노테이션된 Pod가 앱 시작 시 Celery 태스크로 등록된다."""
    # Given: SpakkyApplication with Celery plugin started
    celery_app = app.container.get(CeleryApp)

    # When: Application has started (via fixture)

    # Then: All @task decorated methods are registered with fully qualified names
    registered_tasks = celery_app.task_routes
    email_handler_prefix = "tests.apps.dummy.EmailTaskHandler"
    report_handler_prefix = "tests.apps.dummy.ReportTaskHandler"

    assert f"{email_handler_prefix}.send_email" in registered_tasks
    assert f"{email_handler_prefix}.send_email_async" in registered_tasks
    assert f"{email_handler_prefix}.send_bulk_emails" in registered_tasks
    assert f"{email_handler_prefix}.send_bulk_emails_async" in registered_tasks
    assert f"{report_handler_prefix}.generate_report" in registered_tasks
    assert f"{report_handler_prefix}.generate_report_async" in registered_tasks
    assert f"{report_handler_prefix}.export_report" in registered_tasks
    assert f"{report_handler_prefix}.export_report_async" in registered_tasks


# =============================================================================
# Scenario: Synchronous Task Dispatch via AOP
# =============================================================================


def test_call_email_task_expect_task_executed(
    app: SpakkyApplication,
) -> None:
    """이메일 태스크 메서드 호출 시 Celery를 통해 태스크가 실행된다."""
    # Given: A registered email handler (proxied with CeleryTaskDispatchAspect)
    email_handler = app.container.get(EmailTaskHandler)

    # When: Calling a @task method directly
    email_handler.send_email(
        to="user@example.com",
        subject="Welcome",
        body="Hello, welcome!",
    )

    # Then: Task execution is recorded
    assert execution_record.count("send_email") == 1
    recorded = execution_record.executions[0]
    assert recorded["to"] == "user@example.com"
    assert recorded["subject"] == "Welcome"
    assert recorded["body"] == "Hello, welcome!"


def test_call_multiple_tasks_expect_all_executed(
    app: SpakkyApplication,
) -> None:
    """여러 태스크 메서드 연속 호출 시 모두 실행된다."""
    # Given: Task handlers
    email_handler = app.container.get(EmailTaskHandler)
    report_handler = app.container.get(ReportTaskHandler)

    # When: Calling multiple @task methods
    email_handler.send_email(
        to="admin@example.com",
        subject="Alert",
        body="System alert",
    )
    report_handler.generate_report(
        report_type="sales",
        params={"month": "March"},
    )
    email_handler.send_bulk_emails(
        recipients=["a@test.com", "b@test.com", "c@test.com"],
        subject="Newsletter",
    )

    # Then: All tasks are executed
    assert execution_record.count("send_email") == 1
    assert execution_record.count("generate_report") == 1
    assert execution_record.count("send_bulk_emails") == 1
    assert execution_record.count() == 3


# =============================================================================
# Scenario: Task Handler Isolation
# =============================================================================


def test_task_handlers_are_singletons_expect_same_instance(
    app: SpakkyApplication,
) -> None:
    """TaskHandler Pod는 싱글톤으로 동작한다."""
    # Given: Container with registered task handlers

    # When: Retrieving the same handler multiple times
    handler1 = app.container.get(EmailTaskHandler)
    handler2 = app.container.get(EmailTaskHandler)

    # Then: Same instance is returned
    assert handler1 is handler2


def test_different_handlers_are_independent_expect_separate_executions(
    app: SpakkyApplication,
) -> None:
    """서로 다른 TaskHandler의 태스크는 독립적으로 실행된다."""
    # Given: Task handlers
    email_handler = app.container.get(EmailTaskHandler)
    report_handler = app.container.get(ReportTaskHandler)

    # When: Calling tasks from different handlers
    email_handler.send_email(
        to="test@example.com",
        subject="Test",
        body="Test body",
    )
    report_handler.export_report(
        report_id="report-123",
        format="pdf",
    )

    # Then: Each handler's task is recorded separately
    email_executions = [
        e for e in execution_record.executions if e["task_name"] == "send_email"
    ]
    report_executions = [
        e for e in execution_record.executions if e["task_name"] == "export_report"
    ]
    assert len(email_executions) == 1
    assert len(report_executions) == 1
    assert email_executions[0]["to"] == "test@example.com"
    assert report_executions[0]["report_id"] == "report-123"
