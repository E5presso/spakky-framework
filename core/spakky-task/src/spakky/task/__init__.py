"""Spakky Task package - Task queue abstraction support."""

from spakky.core.application.plugin import Plugin

from spakky.task.direct import DirectTaskExecutor, DirectTaskInvocation
from spakky.task.error import (
    AbstractSpakkyTaskError,
    DuplicateTaskError,
    InvalidScheduleSpecificationError,
    TaskApplicationContextNotFoundError,
    TaskAsyncInvocationRequiredError,
    TaskNotFoundError,
)
from spakky.task.post_processor import TaskRegistrationPostProcessor
from spakky.task.stereotype.crontab import Crontab, Month, Weekday
from spakky.task.stereotype.schedule import ScheduleRoute, schedule
from spakky.task.stereotype.task_handler import (
    TaskAuthMetadata,
    TaskAuthRequirementMetadata,
    TaskHandler,
    TaskRoute,
    collect_task_auth_metadata,
    task,
)

PLUGIN_NAME = Plugin(name="spakky-task")
"""Plugin identifier for the Spakky Task package."""

__all__ = [
    # Stereotype
    "TaskAuthMetadata",
    "TaskAuthRequirementMetadata",
    "TaskHandler",
    "TaskRoute",
    "collect_task_auth_metadata",
    "task",
    "Crontab",
    "Weekday",
    "Month",
    "ScheduleRoute",
    "schedule",
    # Direct execution
    "DirectTaskExecutor",
    "DirectTaskInvocation",
    # Post-Processors
    "TaskRegistrationPostProcessor",
    # Errors
    "AbstractSpakkyTaskError",
    "TaskNotFoundError",
    "TaskApplicationContextNotFoundError",
    "TaskAsyncInvocationRequiredError",
    "DuplicateTaskError",
    "InvalidScheduleSpecificationError",
    # Plugin
    "PLUGIN_NAME",
]
