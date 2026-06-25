"""In-memory task repository plus the async a2a-sdk ``TaskStore`` bridge."""

from collections.abc import Sequence
from typing import override

from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import ListTasksRequest, ListTasksResponse, Task

from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository


class InMemoryA2ATaskRepository(IA2ATaskRepository):
    """Dictionary-backed synchronous A2A task repository."""

    _tasks: dict[str, Task]

    def __init__(self) -> None:
        self._tasks = {}

    @override
    def get_or_none(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    @override
    def save(self, task: Task) -> None:
        self._tasks[task.id] = task

    @override
    def delete(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    @override
    def list_all(self) -> Sequence[Task]:
        return tuple(self._tasks.values())


class SpakkyA2ATaskStore(TaskStore):
    """Async a2a-sdk ``TaskStore`` delegating to a synchronous repository.

    The a2a-sdk request handler awaits every store call, but the plugin's
    repository port is synchronous; each async method calls straight through to
    the in-process repository, which performs no I/O of its own.
    """

    _repository: IA2ATaskRepository

    def __init__(self, repository: IA2ATaskRepository) -> None:
        self._repository = repository

    @override
    async def save(self, task: Task, context: ServerCallContext) -> None:
        self._repository.save(task)

    @override
    async def get(self, task_id: str, context: ServerCallContext) -> Task | None:
        return self._repository.get_or_none(task_id)

    @override
    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        self._repository.delete(task_id)

    @override
    async def list(
        self,
        params: ListTasksRequest,
        context: ServerCallContext,
    ) -> ListTasksResponse:
        tasks = [
            task for task in self._repository.list_all() if self._matches(task, params)
        ]
        return ListTasksResponse(tasks=tasks, total_size=len(tasks))

    @staticmethod
    def _matches(task: Task, params: ListTasksRequest) -> bool:
        """Return whether a task satisfies the context and status filters."""
        if params.context_id and task.context_id != params.context_id:
            return False
        if params.status and task.status.state != params.status:
            return False
        return True
