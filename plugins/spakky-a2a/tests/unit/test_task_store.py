"""Tests for the A2A task repository and the async TaskStore bridge."""

from a2a.server.context import ServerCallContext
from a2a.types import ListTasksRequest, Task, TaskState, TaskStatus

from spakky.plugins.a2a.store.task_store import (
    InMemoryA2ATaskRepository,
    SpakkyA2ATaskStore,
)


def _task(
    task_id: str, *, context_id: str = "ctx", state: TaskState | None = None
) -> Task:
    status = TaskStatus(state=state) if state is not None else TaskStatus()
    return Task(id=task_id, context_id=context_id, status=status)


def test_repository_round_trips_a_saved_task() -> None:
    """A saved task is returned by id from the in-memory repository."""
    repository = InMemoryA2ATaskRepository()
    task = _task("t1")

    repository.save(task)

    assert repository.get_or_none("t1") == task


def test_repository_returns_none_for_missing_task() -> None:
    """An unknown task id resolves to None."""
    assert InMemoryA2ATaskRepository().get_or_none("absent") is None


def test_repository_delete_removes_a_task() -> None:
    """Deleting a task removes it from the repository."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))

    repository.delete("t1")

    assert repository.get_or_none("t1") is None


def test_repository_delete_missing_task_is_a_no_op() -> None:
    """Deleting an absent task leaves the repository unchanged."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))

    repository.delete("absent")

    assert repository.get_or_none("t1") is not None


def test_repository_list_all_returns_every_task() -> None:
    """list_all enumerates every persisted task."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))
    repository.save(_task("t2"))

    assert {task.id for task in repository.list_all()} == {"t1", "t2"}


async def test_store_get_delegates_to_repository() -> None:
    """The async store get returns the repository's snapshot."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))
    store = SpakkyA2ATaskStore(repository)

    result = await store.get("t1", ServerCallContext())

    assert result is not None
    assert result.id == "t1"


async def test_store_save_then_get_round_trips() -> None:
    """The async store save persists through to the repository."""
    store = SpakkyA2ATaskStore(InMemoryA2ATaskRepository())

    await store.save(_task("t1"), ServerCallContext())

    assert await store.get("t1", ServerCallContext()) is not None


async def test_store_delete_delegates_to_repository() -> None:
    """The async store delete removes the snapshot from the repository."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))
    store = SpakkyA2ATaskStore(repository)

    await store.delete("t1", ServerCallContext())

    assert repository.get_or_none("t1") is None


async def test_store_list_filters_by_context_id() -> None:
    """The async store list returns only tasks matching the requested context."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1", context_id="a"))
    repository.save(_task("t2", context_id="b"))
    store = SpakkyA2ATaskStore(repository)

    response = await store.list(ListTasksRequest(context_id="a"), ServerCallContext())

    assert [task.id for task in response.tasks] == ["t1"]
    assert response.total_size == 1


async def test_store_list_filters_by_status() -> None:
    """The async store list returns only tasks matching the requested status."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1", state=TaskState.TASK_STATE_WORKING))
    repository.save(_task("t2", state=TaskState.TASK_STATE_COMPLETED))
    store = SpakkyA2ATaskStore(repository)

    response = await store.list(
        ListTasksRequest(status=TaskState.TASK_STATE_WORKING),
        ServerCallContext(),
    )

    assert [task.id for task in response.tasks] == ["t1"]


async def test_store_list_without_filters_returns_all() -> None:
    """The async store list returns every task when no filter is set."""
    repository = InMemoryA2ATaskRepository()
    repository.save(_task("t1"))
    repository.save(_task("t2"))
    store = SpakkyA2ATaskStore(repository)

    response = await store.list(ListTasksRequest(), ServerCallContext())

    assert {task.id for task in response.tasks} == {"t1", "t2"}
