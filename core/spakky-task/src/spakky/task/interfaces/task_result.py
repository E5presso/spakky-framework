"""Abstract task result handle for background task dispatchers."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from spakky.core.common.interfaces.equatable import IEquatable

T = TypeVar("T")


class AbstractTaskResult(ABC, Generic[T]):
    """Abstract handle for the result of a dispatched background task.

    Concrete adapters (e.g. CeleryTaskResult) implement this for each broker.
    """

    @property
    @abstractmethod
    def task_id(self) -> IEquatable:
        """Unique identifier for the dispatched task."""
        ...

    @abstractmethod
    def get(self) -> T:
        """Block until the task completes and return its result.

        Returns:
            The return value of the executed task method.
        """
        ...
