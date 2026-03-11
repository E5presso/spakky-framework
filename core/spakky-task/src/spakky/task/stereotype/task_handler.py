"""TaskHandler stereotype and task routing decorators.

This module provides @TaskHandler stereotype and @task decorator
for organizing task-queue-driven architectures.
"""

from dataclasses import dataclass
from typing import Callable, TypeVar

from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.pod import Pod

T = TypeVar("T")
"""Type variable for task method return types."""


@dataclass
class TaskRoute(FunctionAnnotation):
    """Annotation for marking methods as dispatchable tasks.

    Associates a method as a task that can be dispatched to a task queue.
    """

    ...


def task(obj: Callable[..., T]) -> Callable[..., T]:
    """Decorator for marking methods as dispatchable tasks.

    Args:
        obj: The method to mark as a task.

    Returns:
        The annotated method.

    Example:
        @TaskHandler()
        class EmailTaskHandler:
            @task
            def send_email(self, to: str, subject: str, body: str) -> None:
                # Task implementation
                pass
    """
    return TaskRoute()(obj)


@dataclass(eq=False)
class TaskHandler(Pod):
    """Stereotype for task handler classes.

    TaskHandlers contain methods decorated with @task that
    can be dispatched to task queues asynchronously.
    """

    ...
