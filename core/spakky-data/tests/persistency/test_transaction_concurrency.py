"""자식 task·thread가 바깥 transaction scope를 이어받을 때의 동작을 검증한다."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from itertools import count
from typing import override
from unittest.mock import MagicMock

import pytest
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.error import TransactionRollbackOnlyError
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
    Propagation,
)


class ContextLocalTransaction(AbstractTransaction):
    """physical transaction 자원(번호)을 실행 context마다 쌓는 기록용 구현.

    실제 구현처럼 "지금 쓰는 자원"을 ContextVar의 불변 tuple로 찾는다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self._ids = count(1)
        self._resources: ContextVar[tuple[int, ...]] = ContextVar(
            "test_resources", default=()
        )
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        return self._resources.get()[-1]

    @override
    def initialize(self) -> None:
        with self._lock:
            resource = next(self._ids)
            self.events.append(f"open:{resource}")
        self._resources.set((*self._resources.get(), resource))

    @override
    def dispose(self) -> None:
        resources = self._resources.get()
        self._resources.set(resources[:-1])
        with self._lock:
            self.events.append(f"close:{resources[-1]}")

    @override
    def commit(self) -> None:
        with self._lock:
            self.events.append(f"commit:{self.current}")

    @override
    def rollback(self) -> None:
        with self._lock:
            self.events.append(f"rollback:{self.current}")


class AsyncContextLocalTransaction(AbstractAsyncTransaction):
    """비동기판 ContextLocalTransaction."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self._ids = count(1)
        self._resources: ContextVar[tuple[int, ...]] = ContextVar(
            "test_async_resources", default=()
        )

    @property
    def current(self) -> int:
        return self._resources.get()[-1]

    @override
    async def initialize(self) -> None:
        resource = next(self._ids)
        self.events.append(f"open:{resource}")
        self._resources.set((*self._resources.get(), resource))

    @override
    async def dispose(self) -> None:
        resources = self._resources.get()
        self._resources.set(resources[:-1])
        self.events.append(f"close:{resources[-1]}")

    @override
    async def commit(self) -> None:
        self.events.append(f"commit:{self.current}")

    @override
    async def rollback(self) -> None:
        self.events.append(f"rollback:{self.current}")


class ChildFailureError(Exception):
    """자식 task에서 올라가는 업무 예외."""


async def test_async_joined_failure_in_child_task_expect_outer_rollback_only() -> None:
    """자식 task에서 합쳐진 scope가 실패하면, 바깥이 그 실패를 삼켜도 commit하지 않는다."""
    transaction = AsyncContextLocalTransaction()

    async def child() -> None:
        async with transaction.scope(Propagation.REQUIRED):
            raise ChildFailureError()

    with pytest.raises(TransactionRollbackOnlyError):
        async with transaction.scope():
            results = await asyncio.gather(child(), return_exceptions=True)
            assert isinstance(results[0], ChildFailureError)
            assert transaction.is_rollback_only is True

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


async def test_async_joined_success_in_child_task_expect_outer_commits_once() -> None:
    """자식 task에서 합쳐진 scope가 정상으로 끝나면 바깥이 한 번만 commit한다."""
    transaction = AsyncContextLocalTransaction()
    seen: list[int] = []

    async def child() -> None:
        async with transaction.scope(Propagation.REQUIRED):
            seen.append(transaction.current)

    async with transaction.scope():
        await asyncio.gather(child(), child())

    assert seen == [1, 1]
    assert transaction.events == ["open:1", "commit:1", "close:1"]


async def test_async_concurrent_requires_new_expect_each_task_keeps_own_transaction() -> (
    None
):
    """동시에 연 REQUIRES_NEW는 서로의 자원을 쓰거나 닫지 않고, 바깥 자원도 그대로다."""
    transaction = AsyncContextLocalTransaction()
    a_opened = asyncio.Event()
    b_opened = asyncio.Event()
    a_done = asyncio.Event()
    seen: dict[str, tuple[int, int]] = {}

    async def a() -> None:
        async with transaction.scope(Propagation.REQUIRES_NEW):
            mine = transaction.current
            a_opened.set()
            await b_opened.wait()
            seen["a"] = (mine, transaction.current)
        a_done.set()

    async def b() -> None:
        await a_opened.wait()
        async with transaction.scope(Propagation.REQUIRES_NEW):
            mine = transaction.current
            b_opened.set()
            await a_done.wait()
            seen["b"] = (mine, transaction.current)

    async with transaction.scope():
        await asyncio.gather(a(), b())
        assert transaction.current == 1

    assert seen == {"a": (2, 2), "b": (3, 3)}
    assert transaction.events == [
        "open:1",
        "open:2",
        "open:3",
        "commit:2",
        "close:2",
        "commit:3",
        "close:3",
        "commit:1",
        "close:1",
    ]


async def test_async_requires_new_in_child_task_expect_parent_scopes_unchanged() -> (
    None
):
    """자식 task가 연 REQUIRES_NEW는 부모 context의 scope에 보이지 않는다."""
    transaction = AsyncContextLocalTransaction()
    child_opened = asyncio.Event()
    parent_checked = asyncio.Event()
    observed: list[bool] = []

    async def child() -> None:
        async with transaction.scope(Propagation.REQUIRES_NEW):
            child_opened.set()
            await parent_checked.wait()
            raise ChildFailureError()

    async with transaction.scope():
        task = asyncio.create_task(child())
        await child_opened.wait()
        observed.append(transaction.is_rollback_only)
        parent_checked.set()
        with pytest.raises(ChildFailureError):
            await task
        observed.append(transaction.is_rollback_only)

    assert observed == [False, False]
    assert transaction.events == [
        "open:1",
        "open:2",
        "rollback:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


def test_sync_joined_failure_in_copied_context_thread_expect_outer_rollback_only() -> (
    None
):
    """context를 복사한 thread에서 합쳐진 scope가 실패하면 바깥은 commit하지 않는다."""
    transaction = ContextLocalTransaction()

    def child() -> None:
        with transaction.scope(Propagation.REQUIRED):
            raise ChildFailureError()

    with pytest.raises(TransactionRollbackOnlyError):
        with transaction.scope():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(copy_context().run, child)
                with pytest.raises(ChildFailureError):
                    future.result()

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


def test_sync_concurrent_requires_new_threads_expect_each_thread_keeps_own() -> None:
    """두 thread가 동시에 연 REQUIRES_NEW는 각자의 자원으로 commit하고 닫는다."""
    transaction = ContextLocalTransaction()
    barrier = threading.Barrier(2)
    seen: dict[str, tuple[int, int]] = {}

    def child(name: str) -> None:
        with transaction.scope(Propagation.REQUIRES_NEW):
            mine = transaction.current
            barrier.wait()
            seen[name] = (mine, transaction.current)
            barrier.wait()

    with transaction.scope():
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(copy_context().run, child, name) for name in "ab"
            ]
            for future in futures:
                future.result()
        assert transaction.current == 1

    assert {mine for mine, _ in seen.values()} == {2, 3}
    assert all(mine == current for mine, current in seen.values())
    assert transaction.events[0] == "open:1"
    assert transaction.events[-2:] == ["commit:1", "close:1"]
    for resource in (2, 3):
        assert transaction.events.index(f"commit:{resource}") < (
            transaction.events.index(f"close:{resource}")
        )


async def test_collector_child_task_collect_expect_in_joined_buffer() -> None:
    """합쳐진 자식 task가 모은 aggregate는 바깥 transaction의 buffer에 들어간다."""
    collector = AggregateCollector()
    outer = MagicMock(spec=AbstractAggregateRoot)
    inner = MagicMock(spec=AbstractAggregateRoot)

    async def child() -> None:
        collector.collect(inner)

    collector.begin_transaction()
    collector.collect(outer)
    await asyncio.create_task(child())
    collector.commit_transaction()

    assert collector.drain_committed() == [outer, inner]


async def test_collector_child_task_own_buffer_expect_isolated_from_parent() -> None:
    """자식 task가 연 buffer(REQUIRES_NEW)는 부모 buffer와 섞이지 않는다."""
    collector = AggregateCollector()
    outer = MagicMock(spec=AbstractAggregateRoot)
    inner = MagicMock(spec=AbstractAggregateRoot)

    async def child() -> list[AbstractAggregateRoot]:
        collector.begin_transaction()
        collector.collect(inner)
        collector.commit_transaction()
        return list(collector.drain_committed())

    collector.begin_transaction()
    collector.collect(outer)
    child_committed = await asyncio.create_task(child())
    collector.commit_transaction()

    assert child_committed == [inner]
    assert collector.drain_committed() == [outer]
