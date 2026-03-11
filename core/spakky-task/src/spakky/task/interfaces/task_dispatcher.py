"""Task dispatcher interfaces for dispatching tasks to task queues.

This module provides unified dispatcher interfaces that handle task dispatching.
Dispatchers are responsible for sending tasks to external task queues (Celery, Taskiq, etc.).
"""

from abc import ABC, abstractmethod
from typing import Callable, ParamSpec

P = ParamSpec("P")
"""ParamSpec for preserving task callable signatures."""

# NOTE: Task return type is typed as `object` because dispatch does not
# return task results. The actual return value is discarded when sending
# to external task queues. If result retrieval is needed, implementations
# should provide separate result-fetching APIs (e.g., AsyncResult in Celery).


class ITaskDispatcher(ABC):
    """Synchronous task dispatcher interface.

    Implementations dispatch tasks to external task queues like Celery or Taskiq.
    """

    @abstractmethod
    def dispatch(
        self,
        task_ref: Callable[P, object],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """Dispatch a task to the task queue.

        Args:
            task_ref: Reference to the task method to dispatch.
            *args: Positional arguments to pass when executed.
            **kwargs: Keyword arguments to pass when executed.
        """
        ...


class IAsyncTaskDispatcher(ABC):
    """Asynchronous task dispatcher interface.

    Implementations dispatch tasks to external task queues like Celery or Taskiq.
    """

    @abstractmethod
    async def dispatch(
        self,
        task_ref: Callable[P, object],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """Dispatch a task to the task queue asynchronously.

        Args:
            task_ref: Reference to the task method to dispatch.
            *args: Positional arguments to pass when executed.
            **kwargs: Keyword arguments to pass when executed.
        """
        ...
