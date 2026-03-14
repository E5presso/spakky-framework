"""Spakky Task package - Task queue abstraction support."""

from spakky.core.application.plugin import Plugin

from spakky.task.error import (
    AbstractSpakkyTaskError,
    DuplicateTaskError,
    InvalidScheduleSpecificationError,
    TaskNotFoundError,
)
from spakky.task.post_processor import TaskRegistrationPostProcessor
from spakky.task.stereotype.crontab import Crontab, Month, Weekday
from spakky.task.stereotype.schedule import ScheduleRoute, schedule
from spakky.task.stereotype.task_handler import (
    TaskHandler,
    TaskRoute,
    task,
)

PLUGIN_NAME = Plugin(name="spakky-task")
"""Plugin identifier for the Spakky Task package."""

__all__ = [
    # Stereotype
    "TaskHandler",
    "TaskRoute",
    "task",
    "Crontab",
    "Weekday",
    "Month",
    "ScheduleRoute",
    "schedule",
    # Post-Processors
    "TaskRegistrationPostProcessor",
    # Errors
    "AbstractSpakkyTaskError",
    "TaskNotFoundError",
    "DuplicateTaskError",
    "InvalidScheduleSpecificationError",
    # Plugin
    "PLUGIN_NAME",
]
