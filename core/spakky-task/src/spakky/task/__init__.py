"""Spakky Task package - Task queue abstraction support."""

from spakky.core.application.plugin import Plugin

from spakky.task.error import (
    AbstractSpakkyTaskError,
    DuplicateTaskError,
    TaskNotFoundError,
)
from spakky.task.interfaces.task_dispatcher import (
    IAsyncTaskDispatcher,
    ITaskDispatcher,
)
from spakky.task.post_processor import TaskRegistrationPostProcessor
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
    # Dispatcher Interfaces
    "ITaskDispatcher",
    "IAsyncTaskDispatcher",
    # Post-Processors
    "TaskRegistrationPostProcessor",
    # Errors
    "AbstractSpakkyTaskError",
    "TaskNotFoundError",
    "DuplicateTaskError",
    # Plugin
    "PLUGIN_NAME",
]
