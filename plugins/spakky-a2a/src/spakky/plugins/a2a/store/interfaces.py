"""Plugin-owned persistence port for A2A task state.

The a2a-sdk ``TaskStore`` ABC is async and threads a ``ServerCallContext``
through every call. This plugin owns a narrower synchronous repository port so
that adapters (in-memory today, a database-backed implementation later) stay
free of a2a-sdk server types; the async bridge lives in ``task_store``.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from a2a.types import Task


class IA2ATaskRepository(ABC):
    """Synchronous persistence port for A2A ``Task`` snapshots."""

    @abstractmethod
    def get_or_none(self, task_id: str) -> Task | None:
        """Return a persisted task by id, or None when absent."""
        ...

    @abstractmethod
    def save(self, task: Task) -> None:
        """Persist or overwrite a task snapshot."""
        ...

    @abstractmethod
    def delete(self, task_id: str) -> None:
        """Remove a task snapshot by id."""
        ...

    @abstractmethod
    def list_all(self) -> Sequence[Task]:
        """Return every persisted task snapshot."""
        ...
