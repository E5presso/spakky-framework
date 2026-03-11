"""Task dispatcher interfaces for dispatching tasks to task queues.

This module provides unified dispatcher interfaces that handle task dispatching.
Dispatchers are responsible for sending tasks to external task queues (Celery, Taskiq, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any

from spakky.core.common.types import Func


class ITaskDispatcher(ABC):
    """Synchronous task dispatcher interface.

    Implementations dispatch tasks to external task queues like Celery or Taskiq.
    """

    @abstractmethod
    def dispatch(self, task_ref: Func, **kwargs: Any) -> None:
        """Dispatch a task to the task queue.

        Args:
            task_ref: Reference to the task method to dispatch.
            **kwargs: Task arguments to pass when executed.
        """
        ...


class IAsyncTaskDispatcher(ABC):
    """Asynchronous task dispatcher interface.

    Implementations dispatch tasks to external task queues like Celery or Taskiq.
    """

    @abstractmethod
    async def dispatch(self, task_ref: Func, **kwargs: Any) -> None:
        """Dispatch a task to the task queue asynchronously.

        Args:
            task_ref: Reference to the task method to dispatch.
            **kwargs: Task arguments to pass when executed.
        """
        ...
