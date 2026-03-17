"""Dummy task handlers for integration tests."""

from dataclasses import dataclass, field
from datetime import time, timedelta
from threading import Lock

from spakky.task.stereotype.crontab import Crontab, Weekday
from spakky.task.stereotype.schedule import schedule
from spakky.task.stereotype.task_handler import TaskHandler, task

__all__ = [
    "TaskExecutionRecord",
    "execution_record",
    "EmailTaskHandler",
    "ReportTaskHandler",
    "AsyncNotificationHandler",
    "AsyncResultTaskHandler",
    "ScheduledTaskHandler",
    "HybridTaskHandler",
]


@dataclass
class TaskExecutionRecord:
    """Records task executions for test assertions."""

    executions: list[dict[str, object]] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(self, task_name: str, **kwargs: object) -> None:
        """Record a task execution."""
        with self._lock:
            self.executions.append({"task_name": task_name, **kwargs})

    def count(self, task_name: str | None = None) -> int:
        """Count executions, optionally filtered by task name."""
        with self._lock:
            if task_name is None:
                return len(self.executions)
            return sum(1 for e in self.executions if e["task_name"] == task_name)

    def clear(self) -> None:
        """Clear all recorded executions."""
        with self._lock:
            self.executions.clear()


# Global record shared across tests
execution_record = TaskExecutionRecord()


@TaskHandler()
class EmailTaskHandler:
    """Task handler for email-related tasks."""

    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Send an email via task queue."""
        execution_record.record(
            "send_email",
            to=to,
            subject=subject,
            body=body,
        )

    @task
    def send_bulk_emails(self, recipients: list[str], subject: str) -> int:
        """Send bulk emails via task queue and return count sent."""
        execution_record.record(
            "send_bulk_emails",
            recipients=recipients,
            subject=subject,
        )
        return len(recipients)


@TaskHandler()
class ReportTaskHandler:
    """Task handler for report generation tasks."""

    @task
    def generate_report(self, report_type: str, params: dict[str, object]) -> str:
        """Generate a report via task queue and return the report ID."""
        execution_record.record(
            "generate_report",
            report_type=report_type,
            params=params,
        )
        return f"report-{report_type}-001"

    @task
    def export_report(self, report_id: str, format: str) -> None:
        """Export a report via task queue to the specified format."""
        execution_record.record(
            "export_report",
            report_id=report_id,
            format=format,
        )


@TaskHandler()
class AsyncNotificationHandler:
    """Task handler with async methods for testing async task dispatch."""

    @task
    async def send_notification(self, user_id: str, message: str) -> None:
        """Send a notification via task queue (async)."""
        execution_record.record(
            "send_notification",
            user_id=user_id,
            message=message,
        )


@TaskHandler()
class AsyncResultTaskHandler:
    """Task handler with a sync @task that returns a value, for get_async() result-retrieval testing."""

    @task
    def compute(self, value: int) -> int:
        """Double the given value via task queue."""
        execution_record.record("compute", value=value)
        return value * 2


@TaskHandler()
class ScheduledTaskHandler:
    """Task handler for scheduled (periodic) tasks."""

    @schedule(interval=timedelta(minutes=30))
    def health_check(self) -> None:
        """Periodic health check every 30 minutes."""
        execution_record.record("health_check")

    @schedule(at=time(3, 0))
    def daily_cleanup(self) -> None:
        """Daily cleanup at 03:00."""
        execution_record.record("daily_cleanup")

    @schedule(
        crontab=Crontab(
            weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY),
            hour=9,
        )
    )
    def triweekly_report(self) -> None:
        """Generate report on Mon/Wed/Fri at 09:00."""
        execution_record.record("triweekly_report")


@TaskHandler()
class HybridTaskHandler:
    """Task handler with methods that have both @task and @schedule.

    Use case: A task that runs on schedule (e.g., daily) but can also
    be triggered manually on-demand.
    """

    @task
    @schedule(interval=timedelta(hours=1))
    def hourly_sync(self) -> None:
        """Sync data every hour, can also be triggered manually."""
        execution_record.record("hourly_sync")
