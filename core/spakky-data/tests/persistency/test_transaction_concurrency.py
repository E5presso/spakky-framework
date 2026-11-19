"""자식 task·thread가 바깥 transaction scope를 이어받을 때의 동작을 검증한다."""

import asyncio
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from itertools import count
from typing import override
from unittest.mock import MagicMock

import pytest
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.error import (
    AggregateBufferNotOpenError,
    TransactionAlreadyFinishedError,
    TransactionRollbackOnlyError,
)
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
    PhysicalTransaction,
    Propagation,
)


@dataclass(eq=False, slots=True)
class Resource:
    """physical transaction 하나의 자원. 그 transaction에 묶여 끝남을 함께 본다."""

    number: int
    transaction: PhysicalTransaction


class ContextLocalTransaction(AbstractTransaction):
    """physical transaction 자원(번호)을 실행 context마다 쌓는 기록용 구현.

    실제 구현처럼 자원을 physical transaction에 묶는다. 자원 stack은 scope를
    그대로 따라가서 합친 scope는 합친 transaction의 자원을 쓰고, 그
    transaction이 끝났으면 아래 자원으로 넘어가지 않고 거절한다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.dispose_hook: Callable[[int], None] | None = None
        self._ids = count(1)
        self._resources: ContextVar[tuple[Resource, ...]] = ContextVar(
            "test_resources", default=()
        )
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        top = self._resources.get()[-1]
        if top.transaction.finished:
            raise TransactionAlreadyFinishedError()
        return top.number

    def write(self) -> None:
        """지금 scope의 자원에 쓰기를 기록한다."""
        number = self.current
        with self._lock:
            self.events.append(f"write:{number}")

    @override
    def initialize(self) -> None:
        with self._lock:
            resource = Resource(next(self._ids), self.current_frame.transaction)
            self.events.append(f"open:{resource.number}")
        self._resources.set((*self._resources.get(), resource))

    @override
    def join(self) -> None:
        resources = self._resources.get()
        joined = next(
            r
            for r in reversed(resources)
            if r.transaction is self.current_frame.transaction
        )
        self._resources.set((*resources, joined))

    @override
    def leave(self) -> None:
        self._resources.set(self._resources.get()[:-1])

    @override
    def dispose(self) -> None:
        resources = self._resources.get()
        if self.dispose_hook is not None:
            self.dispose_hook(resources[-1].number)
        self._resources.set(resources[:-1])
        with self._lock:
            self.events.append(f"close:{resources[-1].number}")

    @override
    def commit(self) -> None:
        number = self.current
        with self._lock:
            self.events.append(f"commit:{number}")

    @override
    def rollback(self) -> None:
        number = self.current
        with self._lock:
            self.events.append(f"rollback:{number}")


class AsyncContextLocalTransaction(AbstractAsyncTransaction):
    """비동기판 ContextLocalTransaction."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.dispose_hook: Callable[[int], Awaitable[None]] | None = None
        self._ids = count(1)
        self._resources: ContextVar[tuple[Resource, ...]] = ContextVar(
            "test_async_resources", default=()
        )

    @property
    def current(self) -> int:
        top = self._resources.get()[-1]
        if top.transaction.finished:
            raise TransactionAlreadyFinishedError()
        return top.number

    def write(self) -> None:
        """지금 scope의 자원에 쓰기를 기록한다."""
        self.events.append(f"write:{self.current}")

    @override
    async def initialize(self) -> None:
        resource = Resource(next(self._ids), self.current_frame.transaction)
        self.events.append(f"open:{resource.number}")
        self._resources.set((*self._resources.get(), resource))

    @override
    async def join(self) -> None:
        resources = self._resources.get()
        joined = next(
            r
            for r in reversed(resources)
            if r.transaction is self.current_frame.transaction
        )
        self._resources.set((*resources, joined))

    @override
    async def leave(self) -> None:
        self._resources.set(self._resources.get()[:-1])

    @override
    async def dispose(self) -> None:
        resources = self._resources.get()
        if self.dispose_hook is not None:
            await self.dispose_hook(resources[-1].number)
        self._resources.set(resources[:-1])
        self.events.append(f"close:{resources[-1].number}")

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

    collector.begin_transaction(PhysicalTransaction())
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
        collector.begin_transaction(PhysicalTransaction())
        collector.collect(inner)
        collector.commit_transaction()
        return list(collector.drain_committed())

    collector.begin_transaction(PhysicalTransaction())
    collector.collect(outer)
    child_committed = await asyncio.create_task(child())
    collector.commit_transaction()

    assert child_committed == [inner]
    assert collector.drain_committed() == [outer]


async def test_async_child_task_begun_after_outer_finished_expect_own_transaction() -> (
    None
):
    """바깥이 끝난 뒤 시작한 자식 task의 REQUIRED는 새 transaction을 열어 commit한다."""
    transaction = AsyncContextLocalTransaction()
    outer_finished = asyncio.Event()
    seen: list[tuple[bool, int]] = []

    async def child() -> None:
        await outer_finished.wait()
        before = transaction.is_active
        async with transaction.scope(Propagation.REQUIRED):
            seen.append((before, transaction.current))

    async with transaction.scope():
        task = asyncio.create_task(child())
    outer_finished.set()
    await task

    assert seen == [(False, 2)]
    assert transaction.events == [
        "open:1",
        "commit:1",
        "close:1",
        "open:2",
        "commit:2",
        "close:2",
    ]


async def test_async_child_task_begun_after_inner_finished_expect_join_live_outer() -> (
    None
):
    """끝난 REQUIRES_NEW 아래에 살아 있는 바깥이 있으면 자식 task는 그 바깥에 합친다."""
    transaction = AsyncContextLocalTransaction()
    inner_finished = asyncio.Event()
    seen: list[int] = []

    async def child() -> None:
        await inner_finished.wait()
        async with transaction.scope(Propagation.REQUIRED):
            seen.append(transaction.current)

    async with transaction.scope():
        async with transaction.scope(Propagation.REQUIRES_NEW):
            task = asyncio.create_task(child())
        inner_finished.set()
        await task

    assert seen == [1]
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


async def test_async_child_task_failure_after_outer_finished_expect_own_rollback() -> (
    None
):
    """바깥이 끝난 뒤 시작한 자식 task가 실패하면 자기 transaction만 rollback한다."""
    transaction = AsyncContextLocalTransaction()
    outer_finished = asyncio.Event()

    async def child() -> None:
        await outer_finished.wait()
        async with transaction.scope(Propagation.REQUIRED):
            raise ChildFailureError()

    async with transaction.scope():
        task = asyncio.create_task(child())
    outer_finished.set()
    with pytest.raises(ChildFailureError):
        await task

    assert transaction.events == [
        "open:1",
        "commit:1",
        "close:1",
        "open:2",
        "rollback:2",
        "close:2",
    ]


async def test_async_joined_child_task_outliving_outer_expect_already_finished() -> (
    None
):
    """합쳐진 자식 task가 바깥이 끝난 뒤 scope를 나가면 TransactionAlreadyFinishedError가 난다."""
    transaction = AsyncContextLocalTransaction()
    child_joined = asyncio.Event()
    outer_finished = asyncio.Event()

    async def child() -> None:
        async with transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            await outer_finished.wait()

    async with transaction.scope():
        task = asyncio.create_task(child())
        await child_joined.wait()
    outer_finished.set()
    with pytest.raises(TransactionAlreadyFinishedError):
        await task

    assert transaction.events == ["open:1", "commit:1", "close:1"]


async def test_async_joined_child_task_failing_after_outer_expect_already_finished() -> (
    None
):
    """합쳐진 자식 task가 바깥이 끝난 뒤 실패해도 TransactionAlreadyFinishedError로 알린다."""
    transaction = AsyncContextLocalTransaction()
    child_joined = asyncio.Event()
    outer_finished = asyncio.Event()

    async def child() -> None:
        async with transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            await outer_finished.wait()
            raise ChildFailureError()

    async with transaction.scope():
        task = asyncio.create_task(child())
        await child_joined.wait()
    outer_finished.set()
    with pytest.raises(TransactionAlreadyFinishedError) as raised:
        await task

    assert isinstance(raised.value.__context__, ChildFailureError)
    assert transaction.events == ["open:1", "commit:1", "close:1"]


def test_sync_thread_begun_after_outer_finished_expect_own_transaction() -> None:
    """바깥이 끝난 뒤 시작한 thread의 REQUIRED는 새 transaction을 열어 commit한다."""
    transaction = ContextLocalTransaction()
    outer_finished = threading.Event()
    seen: list[tuple[bool, int]] = []

    def child() -> None:
        outer_finished.wait()
        before = transaction.is_active
        with transaction.scope(Propagation.REQUIRED):
            seen.append((before, transaction.current))

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            future = executor.submit(copy_context().run, child)
        outer_finished.set()
        future.result()

    assert seen == [(False, 2)]
    assert transaction.events == [
        "open:1",
        "commit:1",
        "close:1",
        "open:2",
        "commit:2",
        "close:2",
    ]


def test_sync_thread_begun_after_inner_finished_expect_join_live_outer() -> None:
    """끝난 REQUIRES_NEW 아래에 살아 있는 바깥이 있으면 thread는 그 바깥에 합친다."""
    transaction = ContextLocalTransaction()
    inner_finished = threading.Event()
    seen: list[int] = []

    def child() -> None:
        inner_finished.wait()
        with transaction.scope(Propagation.REQUIRED):
            seen.append(transaction.current)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            with transaction.scope(Propagation.REQUIRES_NEW):
                future = executor.submit(copy_context().run, child)
            inner_finished.set()
            future.result()

    assert seen == [1]
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


def test_sync_joined_thread_outliving_outer_expect_already_finished_error() -> None:
    """합쳐진 thread가 바깥이 끝난 뒤 scope를 나가면 TransactionAlreadyFinishedError가 난다."""
    transaction = ContextLocalTransaction()
    child_joined = threading.Event()
    outer_finished = threading.Event()

    def child() -> None:
        with transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            outer_finished.wait()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            future = executor.submit(copy_context().run, child)
            child_joined.wait()
        outer_finished.set()
        with pytest.raises(TransactionAlreadyFinishedError):
            future.result()

    assert transaction.events == ["open:1", "commit:1", "close:1"]


def test_sync_joined_thread_failing_after_outer_expect_already_finished() -> None:
    """합쳐진 thread가 바깥이 끝난 뒤 실패해도 TransactionAlreadyFinishedError로 알린다."""
    transaction = ContextLocalTransaction()
    child_joined = threading.Event()
    outer_finished = threading.Event()

    def child() -> None:
        with transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            outer_finished.wait()
            raise ChildFailureError()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            future = executor.submit(copy_context().run, child)
            child_joined.wait()
        outer_finished.set()
        with pytest.raises(TransactionAlreadyFinishedError) as raised:
            future.result()

    assert isinstance(raised.value.__context__, ChildFailureError)
    assert transaction.events == ["open:1", "commit:1", "close:1"]


async def test_collector_child_task_after_outer_finished_expect_refused_then_own() -> (
    None
):
    """바깥이 끝난 뒤의 자식 task는 그 buffer에 모으지 못하고, 새로 연 buffer에 모은다."""
    collector = AggregateCollector()
    outer_tx = PhysicalTransaction()
    outer = MagicMock(spec=AbstractAggregateRoot)
    inner = MagicMock(spec=AbstractAggregateRoot)
    outer_committed = asyncio.Event()

    async def child() -> list[AbstractAggregateRoot]:
        await outer_committed.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            collector.collect(inner)
        collector.begin_transaction(PhysicalTransaction())
        collector.collect(inner)
        collector.commit_transaction()
        return list(collector.drain_committed())

    collector.begin_transaction(outer_tx)
    collector.collect(outer)
    task = asyncio.create_task(child())
    outer_tx.finished = True
    collector.commit_transaction()
    outer_committed.set()

    assert await task == [inner]
    assert collector.drain_committed() == [outer]


async def test_collector_child_task_after_inner_finished_expect_refused() -> None:
    """끝난 안쪽 transaction의 buffer는 아래 buffer로 넘기지 않고 aggregate를 거절한다."""
    collector = AggregateCollector()
    outer_tx = PhysicalTransaction()
    inner_tx = PhysicalTransaction()
    outer = MagicMock(spec=AbstractAggregateRoot)
    late = MagicMock(spec=AbstractAggregateRoot)
    inner_finished = asyncio.Event()

    async def child() -> None:
        await inner_finished.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            collector.collect(late)

    collector.begin_transaction(outer_tx)
    collector.collect(outer)
    collector.begin_transaction(inner_tx)
    task = asyncio.create_task(child())
    inner_tx.finished = True
    inner_finished.set()
    await task
    collector.commit_transaction()
    collector.commit_transaction()

    assert collector.drain_committed() == [outer]


async def test_collector_child_task_joining_outer_after_inner_expect_outer_buffer() -> (
    None
):
    """안쪽이 끝난 뒤 바깥에 합친 자식 task는 바깥 transaction의 buffer에 모은다."""
    collector = AggregateCollector()
    outer_tx = PhysicalTransaction()
    inner_tx = PhysicalTransaction()
    outer = MagicMock(spec=AbstractAggregateRoot)
    late = MagicMock(spec=AbstractAggregateRoot)
    inner_finished = asyncio.Event()

    async def child() -> None:
        await inner_finished.wait()
        collector.join_transaction(outer_tx)
        collector.collect(late)
        collector.leave_transaction()

    collector.begin_transaction(outer_tx)
    collector.collect(outer)
    collector.begin_transaction(inner_tx)
    task = asyncio.create_task(child())
    inner_tx.finished = True
    collector.commit_transaction()
    inner_finished.set()
    await task

    assert collector.drain_committed() == []
    collector.commit_transaction()
    assert collector.drain_committed() == [outer, late]


async def test_collector_child_task_close_inherited_closed_buffer_expect_error() -> (
    None
):
    """자식 task가 이어받은 buffer가 이미 닫혔으면 그 buffer를 다시 닫을 수 없다."""
    collector = AggregateCollector()
    outer_committed = asyncio.Event()
    errors: list[type[BaseException]] = []

    async def child() -> None:
        await outer_committed.wait()
        for close in (collector.commit_transaction, collector.discard_transaction):
            with pytest.raises(AggregateBufferNotOpenError) as raised:
                close()
            errors.append(raised.type)

    collector.begin_transaction(PhysicalTransaction())
    task = asyncio.create_task(child())
    collector.commit_transaction()
    outer_committed.set()
    await task

    assert errors == [AggregateBufferNotOpenError, AggregateBufferNotOpenError]
    assert collector.drain_committed() == []


class OuterFailureError(Exception):
    """바깥 use case에서 올라가는 업무 예외."""


async def test_async_child_joining_while_inner_disposes_expect_outer_resource_and_buffer() -> (
    None
):
    """안쪽 REQUIRES_NEW가 dispose하는 사이 시작한 자식 task는 바깥의 자원과 buffer를 함께 쓴다.

    안쪽 commit 뒤에 나간 aggregate에 그 쓰기가 섞이지 않고, 바깥이 rollback되면
    쓰기와 aggregate가 함께 사라진다.
    """
    transaction = AsyncContextLocalTransaction()
    collector = AggregateCollector()
    aspect = AsyncTransactionalAspect(
        transaction, collector, TransactionSynchronization()
    )
    child_aggregate = MagicMock(spec=AbstractAggregateRoot)
    disposing = asyncio.Event()
    child_done = asyncio.Event()
    published: list[AbstractAggregateRoot] = []
    tasks: list[asyncio.Task[None]] = []

    async def hold_inner_dispose(number: int) -> None:
        if number == 2:
            disposing.set()
            await child_done.wait()

    transaction.dispose_hook = hold_inner_dispose

    @Transactional()
    async def child_write() -> None:
        transaction.write()
        collector.collect(child_aggregate)

    async def child() -> None:
        await disposing.wait()
        await aspect.around_async(child_write)
        child_done.set()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def inner() -> None:
        tasks.append(asyncio.create_task(child()))

    @Transactional()
    async def outer() -> None:
        await aspect.around_async(inner)
        published.extend(collector.drain_committed())
        await tasks[0]
        raise OuterFailureError()

    with pytest.raises(OuterFailureError):
        await aspect.around_async(outer)

    assert published == []
    assert collector.drain_committed() == []
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "write:1",
        "close:2",
        "rollback:1",
        "close:1",
    ]


async def test_async_child_joined_to_finished_inner_expect_write_refused() -> None:
    """안쪽에 합친 자식 task는 안쪽이 끝난 뒤 바깥의 자원으로 넘어가 쓰지 않고 거절된다."""
    transaction = AsyncContextLocalTransaction()
    collector = AggregateCollector()
    aspect = AsyncTransactionalAspect(
        transaction, collector, TransactionSynchronization()
    )
    child_aggregate = MagicMock(spec=AbstractAggregateRoot)
    child_joined = asyncio.Event()
    inner_finished = asyncio.Event()
    refused: list[type[BaseException]] = []
    tasks: list[asyncio.Task[None]] = []

    @Transactional()
    async def child_write() -> None:
        child_joined.set()
        await inner_finished.wait()
        for write in (transaction.write, lambda: collector.collect(child_aggregate)):
            with pytest.raises(TransactionAlreadyFinishedError) as raised:
                write()
            refused.append(raised.type)

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def inner() -> None:
        tasks.append(asyncio.create_task(aspect.around_async(child_write)))
        await child_joined.wait()

    @Transactional()
    async def outer() -> None:
        await aspect.around_async(inner)
        inner_finished.set()
        with pytest.raises(TransactionAlreadyFinishedError):
            await tasks[0]

    await aspect.around_async(outer)

    assert refused == [TransactionAlreadyFinishedError, TransactionAlreadyFinishedError]
    assert collector.drain_committed() == []
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


def test_sync_thread_joining_while_inner_disposes_expect_outer_resource_and_buffer() -> (
    None
):
    """안쪽 REQUIRES_NEW가 dispose하는 사이 시작한 thread는 바깥의 자원과 buffer를 함께 쓴다."""
    transaction = ContextLocalTransaction()
    collector = AggregateCollector()
    aspect = TransactionalAspect(transaction, collector, TransactionSynchronization())
    child_aggregate = MagicMock(spec=AbstractAggregateRoot)
    disposing = threading.Event()
    child_done = threading.Event()
    published: list[AbstractAggregateRoot] = []
    executor = ThreadPoolExecutor(max_workers=1)

    def hold_inner_dispose(number: int) -> None:
        if number == 2:
            disposing.set()
            child_done.wait()

    transaction.dispose_hook = hold_inner_dispose

    @Transactional()
    def child_write() -> None:
        transaction.write()
        collector.collect(child_aggregate)

    def child() -> None:
        disposing.wait()
        aspect.around(child_write)
        child_done.set()

    futures: list[Future[None]] = []

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def inner() -> None:
        futures.append(executor.submit(copy_context().run, child))

    @Transactional()
    def outer() -> None:
        aspect.around(inner)
        published.extend(collector.drain_committed())
        futures[0].result()
        raise OuterFailureError()

    with executor, pytest.raises(OuterFailureError):
        aspect.around(outer)

    assert published == []
    assert collector.drain_committed() == []
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "write:1",
        "close:2",
        "rollback:1",
        "close:1",
    ]


def test_sync_thread_joined_to_finished_inner_expect_write_refused() -> None:
    """안쪽에 합친 thread는 안쪽이 끝난 뒤 바깥의 자원으로 넘어가 쓰지 않고 거절된다."""
    transaction = ContextLocalTransaction()
    collector = AggregateCollector()
    aspect = TransactionalAspect(transaction, collector, TransactionSynchronization())
    child_aggregate = MagicMock(spec=AbstractAggregateRoot)
    child_joined = threading.Event()
    inner_finished = threading.Event()
    refused: list[type[BaseException]] = []
    futures: list[Future[None]] = []
    executor = ThreadPoolExecutor(max_workers=1)

    @Transactional()
    def child_write() -> None:
        child_joined.set()
        inner_finished.wait()
        for write in (transaction.write, lambda: collector.collect(child_aggregate)):
            with pytest.raises(TransactionAlreadyFinishedError) as raised:
                write()
            refused.append(raised.type)

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def inner() -> None:
        futures.append(executor.submit(copy_context().run, aspect.around, child_write))
        child_joined.wait()

    @Transactional()
    def outer() -> None:
        aspect.around(inner)
        inner_finished.set()
        with pytest.raises(TransactionAlreadyFinishedError):
            futures[0].result()

    with executor:
        aspect.around(outer)

    assert refused == [TransactionAlreadyFinishedError, TransactionAlreadyFinishedError]
    assert collector.drain_committed() == []
    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]
