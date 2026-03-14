"""Unit tests for Celery task dispatch via full SpakkyApplication.

Verifies that @task methods are intercepted by CeleryTaskDispatchAspect
and dispatched to the broker via send_task().
"""

from celery import Celery
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.celery.common.task_result import CeleryTaskResult
from tests.apps.dummy import (
    EmailTaskHandler,
    ReportTaskHandler,
)

# =============================================================================
# Scenario: Task Registration
# =============================================================================


def test_task_handlers_registered_on_app_start_expect_tasks_in_celery(
    app: SpakkyApplication,
) -> None:
    """TaskHandler로 어노테이션된 Pod가 앱 시작 시 Celery 태스크로 등록된다."""
    # Given: SpakkyApplication with Celery plugin started
    celery = app.container.get(Celery)

    # When: Application has started (via fixture)

    # Then: All @task decorated methods are registered with fully qualified names
    registered_tasks = celery.tasks
    email_handler_prefix = "tests.apps.dummy.EmailTaskHandler"
    report_handler_prefix = "tests.apps.dummy.ReportTaskHandler"

    assert f"{email_handler_prefix}.send_email" in registered_tasks
    assert f"{email_handler_prefix}.send_bulk_emails" in registered_tasks
    assert f"{report_handler_prefix}.generate_report" in registered_tasks
    assert f"{report_handler_prefix}.export_report" in registered_tasks


def test_scheduled_tasks_registered_in_beat_schedule(
    app: SpakkyApplication,
) -> None:
    """@schedule 메서드가 Celery beat_schedule에 등록된다."""
    celery = app.container.get(Celery)
    beat_schedule = celery.conf.beat_schedule
    scheduled_prefix = "tests.apps.dummy.ScheduledTaskHandler"

    assert f"{scheduled_prefix}.health_check" in beat_schedule
    assert f"{scheduled_prefix}.daily_cleanup" in beat_schedule
    assert f"{scheduled_prefix}.triweekly_report" in beat_schedule


# =============================================================================
# Scenario: Task Dispatch via AOP
# =============================================================================


def test_call_task_method_expect_dispatched_and_returns_task_result(
    app: SpakkyApplication,
) -> None:
    """@task 메서드 호출 시 send_task()로 디스패치되고 CeleryTaskResult를 반환한다."""
    # Given: A registered email handler (proxied with CeleryTaskDispatchAspect)
    email_handler = app.container.get(EmailTaskHandler)

    # When: Calling a @task method
    result = email_handler.send_email(
        to="user@example.com",
        subject="Welcome",
        body="Hello, welcome!",
    )

    # Then: Returns CeleryTaskResult (task dispatched via send_task)
    assert isinstance(result, CeleryTaskResult)


def test_call_multiple_tasks_expect_all_return_task_results(
    app: SpakkyApplication,
) -> None:
    """여러 @task 메서드 호출 시 모두 CeleryTaskResult를 반환한다."""
    # Given: Task handlers
    email_handler = app.container.get(EmailTaskHandler)
    report_handler = app.container.get(ReportTaskHandler)

    # When: Calling multiple @task methods
    result1 = email_handler.send_email(
        to="admin@example.com",
        subject="Alert",
        body="System alert",
    )
    result2 = report_handler.generate_report(
        report_type="sales",
        params={"month": "March"},
    )
    result3 = email_handler.send_bulk_emails(
        recipients=["a@test.com", "b@test.com", "c@test.com"],
        subject="Newsletter",
    )

    # Then: All return CeleryTaskResult
    assert isinstance(result1, CeleryTaskResult)
    assert isinstance(result2, CeleryTaskResult)
    assert isinstance(result3, CeleryTaskResult)


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
