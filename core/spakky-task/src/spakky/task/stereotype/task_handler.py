"""TaskHandler stereotype and task routing decorators.

This module provides @TaskHandler stereotype and @task decorator
for organizing task-queue-driven architectures.
"""

from dataclasses import dataclass
from typing import Callable, Literal, ParamSpec, TypeVar, cast, overload

from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.pod import Pod

from spakky.task.interfaces.task_result import AbstractTaskResult

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class TaskRoute(FunctionAnnotation):
    """Annotation for marking methods as dispatchable tasks.

    Associates a method as a task that can be dispatched to a task queue.
    """

    background: bool = False
    """If True, dispatch to the task queue. If False (default), execute immediately."""


@overload
def task(obj: Callable[P, T]) -> Callable[P, T]: ...


@overload
def task(
    *, background: Literal[False] = ...
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


@overload
def task(
    *, background: Literal[True]
) -> Callable[[Callable[P, T]], Callable[P, AbstractTaskResult[T]]]: ...


def task(
    obj: Callable[P, T] | None = None,
    *,
    background: bool = False,
) -> (
    Callable[P, T]
    | Callable[[Callable[P, T]], Callable[P, T]]
    | Callable[[Callable[P, T]], Callable[P, AbstractTaskResult[T]]]
):
    """Decorator for marking methods as dispatchable tasks.

    Example:
        @TaskHandler()
        class EmailTaskHandler:
            @task
            def send_email(self, to: str, subject: str, body: str) -> None:
                # Executed immediately (default)
                pass

            @task(background=True)
            def send_bulk_emails(self, recipients: list[str]) -> None:
                # Dispatched to task queue (background)
                pass

    Args:
        obj: The method to mark as a task (when used without arguments).
        background: If True, dispatch to queue. If False (default), execute immediately.

    Returns:
        The annotated method, or a decorator if called with arguments.
    """
    route = TaskRoute(background=background)
    if obj is not None:
        return cast(Callable[P, T], route(obj))
    return route


@dataclass(eq=False)
class TaskHandler(Pod):
    """Stereotype for task handler classes.

    TaskHandlers contain methods decorated with @task that
    can be dispatched to task queues asynchronously.
    """

    ...
