"""Dummy task handlers for integration tests."""

from dataclasses import dataclass, field
from threading import Lock

from spakky.task.stereotype.task_handler import TaskHandler, task


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
        """Send an email immediately (background=False)."""
        execution_record.record(
            "send_email",
            to=to,
            subject=subject,
            body=body,
        )

    @task(background=True)
    def send_email_async(self, to: str, subject: str, body: str) -> None:
        """Send an email via broker (background=True)."""
        execution_record.record(
            "send_email_async",
            to=to,
            subject=subject,
            body=body,
        )

    @task
    def send_bulk_emails(self, recipients: list[str], subject: str) -> int:
        """Send bulk emails immediately and return count sent."""
        execution_record.record(
            "send_bulk_emails",
            recipients=recipients,
            subject=subject,
        )
        return len(recipients)

    @task(background=True)
    def send_bulk_emails_async(self, recipients: list[str], subject: str) -> int:
        """Send bulk emails via broker and return count sent."""
        execution_record.record(
            "send_bulk_emails_async",
            recipients=recipients,
            subject=subject,
        )
        return len(recipients)


@TaskHandler()
class ReportTaskHandler:
    """Task handler for report generation tasks."""

    @task
    def generate_report(self, report_type: str, params: dict[str, object]) -> str:
        """Generate a report immediately and return the report ID."""
        execution_record.record(
            "generate_report",
            report_type=report_type,
            params=params,
        )
        return f"report-{report_type}-001"

    @task(background=True)
    def generate_report_async(self, report_type: str, params: dict[str, object]) -> str:
        """Generate a report via broker and return the report ID."""
        execution_record.record(
            "generate_report_async",
            report_type=report_type,
            params=params,
        )
        return f"report-{report_type}-001"

    @task
    def export_report(self, report_id: str, format: str) -> None:
        """Export a report immediately to the specified format."""
        execution_record.record(
            "export_report",
            report_id=report_id,
            format=format,
        )

    @task(background=True)
    def export_report_async(self, report_id: str, format: str) -> None:
        """Export a report via broker to the specified format."""
        execution_record.record(
            "export_report_async",
            report_id=report_id,
            format=format,
        )
