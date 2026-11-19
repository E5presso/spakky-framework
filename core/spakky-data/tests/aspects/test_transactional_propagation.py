"""@Transactional 메서드의 중첩 호출(propagation)을 검증한다."""

import asyncio
from typing import override
from unittest.mock import MagicMock

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Propagation,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.error import TransactionRollbackOnlyError
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


class InnerFailureError(Exception):
    """안쪽 use case에서 올라가는 업무 예외."""


@Pod()
class RecordingTransaction(AbstractTransaction):
    """physical transaction의 수명 사건을 번호와 함께 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.opened = 0
        self.stack: list[int] = []

    @override
    def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)
        self.events.append(f"open:{self.opened}")

    @override
    def dispose(self) -> None:
        self.events.append(f"close:{self.stack.pop()}")

    @override
    def commit(self) -> None:
        self.events.append(f"commit:{self.stack[-1]}")

    @override
    def rollback(self) -> None:
        self.events.append(f"rollback:{self.stack[-1]}")


@Pod()
class AsyncRecordingTransaction(AbstractAsyncTransaction):
    """비동기 physical transaction의 수명 사건을 번호와 함께 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.opened = 0
        self.stack: list[int] = []

    @override
    async def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)
        self.events.append(f"open:{self.opened}")

    @override
    async def dispose(self) -> None:
        self.events.append(f"close:{self.stack.pop()}")

    @override
    async def commit(self) -> None:
        self.events.append(f"commit:{self.stack[-1]}")

    @override
    async def rollback(self) -> None:
        self.events.append(f"rollback:{self.stack[-1]}")


INNER = MagicMock(spec=AbstractAggregateRoot)
OUTER = MagicMock(spec=AbstractAggregateRoot)


@UseCase()
class InnerUseCase:
    """안쪽에서 aggregate를 저장하는 use case."""

    def __init__(self, collector: AggregateCollector) -> None:
        self.collector = collector

    @Transactional()
    def joined(self) -> None:
        self.collector.collect(INNER)

    @Transactional()
    def joined_failing(self) -> None:
        self.collector.collect(INNER)
        raise InnerFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def separate(self) -> None:
        self.collector.collect(INNER)

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def separate_failing(self) -> None:
        self.collector.collect(INNER)
        raise InnerFailureError()

    @Transactional()
    async def joined_async(self) -> None:
        self.collector.collect(INNER)

    @Transactional()
    async def joined_failing_async(self) -> None:
        self.collector.collect(INNER)
        raise InnerFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def separate_async(self) -> None:
        self.collector.collect(INNER)

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def separate_failing_async(self) -> None:
        self.collector.collect(INNER)
        raise InnerFailureError()


@UseCase()
class OuterUseCase:
    """안쪽 use case를 부르는 바깥 use case."""

    def __init__(self, inner: InnerUseCase, collector: AggregateCollector) -> None:
        self.inner = inner
        self.collector = collector
        self.committed_inside: list[AbstractAggregateRoot] = []

    @Transactional()
    def call_joined(self) -> None:
        self.collector.collect(OUTER)
        self.inner.joined()
        self.committed_inside = list(self.collector.drain_committed())

    @Transactional()
    def swallow_joined_failure(self) -> None:
        try:
            self.inner.joined_failing()
        except InnerFailureError:
            return

    @Transactional()
    def call_separate(self) -> None:
        self.collector.collect(OUTER)
        self.inner.separate()
        self.committed_inside = list(self.collector.drain_committed())

    @Transactional()
    def swallow_separate_failure(self) -> None:
        self.collector.collect(OUTER)
        try:
            self.inner.separate_failing()
        except InnerFailureError:
            return

    @Transactional()
    async def call_joined_async(self) -> None:
        self.collector.collect(OUTER)
        await self.inner.joined_async()
        self.committed_inside = list(self.collector.drain_committed())

    @Transactional()
    async def swallow_joined_failure_async(self) -> None:
        try:
            await self.inner.joined_failing_async()
        except InnerFailureError:
            return

    @Transactional()
    async def call_separate_async(self) -> None:
        self.collector.collect(OUTER)
        await self.inner.separate_async()
        self.committed_inside = list(self.collector.drain_committed())

    @Transactional()
    async def gather_joined_async(self) -> None:
        self.collector.collect(OUTER)
        await asyncio.gather(self.inner.joined_async())

    @Transactional()
    async def gather_swallow_joined_failure_async(self) -> None:
        await asyncio.gather(self.inner.joined_failing_async(), return_exceptions=True)

    @Transactional()
    async def swallow_separate_failure_async(self) -> None:
        self.collector.collect(OUTER)
        try:
            await self.inner.separate_failing_async()
        except InnerFailureError:
            return


@pytest.fixture(name="context")
def context_fixture() -> ApplicationContext:
    """기록용 transaction과 양쪽 aspect를 올린 컨텍스트."""
    context = ApplicationContext()
    context.add(RecordingTransaction)
    context.add(AsyncRecordingTransaction)
    context.add(AggregateCollector)
    context.add(InnerUseCase)
    context.add(OuterUseCase)
    context.add(TransactionalAspect)
    context.add(AsyncTransactionalAspect)
    context.start()
    return context


def test_transactional_default_propagation_expect_required() -> None:
    """propagation을 주지 않으면 REQUIRED다(하위 호환)."""
    assert Transactional().propagation is Propagation.REQUIRED


def test_transactional_joined_call_expect_one_commit_after_outer(
    context: ApplicationContext,
) -> None:
    """합쳐진 안쪽은 commit하지 않고, aggregate는 바깥 commit 뒤에 함께 넘어간다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    outer.call_joined()

    assert context.get(type_=RecordingTransaction).events == [
        "open:1",
        "commit:1",
        "close:1",
    ]
    assert outer.committed_inside == []
    assert collector.drain_committed() == [OUTER, INNER]


def test_transactional_joined_failure_swallowed_expect_rollback_only_error(
    context: ApplicationContext,
) -> None:
    """바깥이 안쪽 실패를 삼켜도 전체가 rollback되고 TransactionRollbackOnlyError가 난다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    with pytest.raises(TransactionRollbackOnlyError):
        outer.swallow_joined_failure()

    assert context.get(type_=RecordingTransaction).events == [
        "open:1",
        "rollback:1",
        "close:1",
    ]
    assert collector.drain_committed() == []
    assert collector.all() == []


def test_transactional_requires_new_expect_inner_committed_first(
    context: ApplicationContext,
) -> None:
    """REQUIRES_NEW 안쪽은 먼저 따로 commit되고, 그 aggregate가 먼저 넘어간다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    outer.call_separate()

    assert context.get(type_=RecordingTransaction).events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]
    assert outer.committed_inside == [INNER]
    assert collector.drain_committed() == [OUTER]


def test_transactional_requires_new_failure_expect_outer_commits_alone(
    context: ApplicationContext,
) -> None:
    """REQUIRES_NEW 안쪽 실패는 그 aggregate만 버리고 바깥은 commit된다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    outer.swallow_separate_failure()

    assert context.get(type_=RecordingTransaction).events == [
        "open:1",
        "open:2",
        "rollback:2",
        "close:2",
        "commit:1",
        "close:1",
    ]
    assert collector.drain_committed() == [OUTER]


async def test_async_transactional_joined_call_expect_one_commit_after_outer(
    context: ApplicationContext,
) -> None:
    """비동기 합쳐진 안쪽도 바깥 commit 뒤에 aggregate가 함께 넘어간다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    await outer.call_joined_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "commit:1",
        "close:1",
    ]
    assert outer.committed_inside == []
    assert collector.drain_committed() == [OUTER, INNER]


async def test_async_transactional_joined_failure_swallowed_expect_rollback_only(
    context: ApplicationContext,
) -> None:
    """비동기에서도 삼킨 안쪽 실패는 전체 rollback과 TransactionRollbackOnlyError로 끝난다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    with pytest.raises(TransactionRollbackOnlyError):
        await outer.swallow_joined_failure_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "rollback:1",
        "close:1",
    ]
    assert collector.drain_committed() == []


async def test_async_transactional_requires_new_expect_inner_committed_first(
    context: ApplicationContext,
) -> None:
    """비동기 REQUIRES_NEW 안쪽은 먼저 따로 commit된다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    await outer.call_separate_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]
    assert outer.committed_inside == [INNER]
    assert collector.drain_committed() == [OUTER]


async def test_async_transactional_requires_new_failure_expect_outer_commits(
    context: ApplicationContext,
) -> None:
    """비동기 REQUIRES_NEW 안쪽 실패는 바깥 commit을 막지 않는다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    await outer.swallow_separate_failure_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "open:2",
        "rollback:2",
        "close:2",
        "commit:1",
        "close:1",
    ]
    assert collector.drain_committed() == [OUTER]


async def test_async_transactional_joined_in_child_task_expect_aggregates_committed(
    context: ApplicationContext,
) -> None:
    """gather로 부른 자식 task가 합쳐지면 그 aggregate도 바깥 commit 뒤에 넘어간다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    await outer.gather_joined_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "commit:1",
        "close:1",
    ]
    assert collector.drain_committed() == [OUTER, INNER]


async def test_async_transactional_joined_failure_in_child_task_expect_rollback_only(
    context: ApplicationContext,
) -> None:
    """gather로 부른 자식 task의 합쳐진 실패를 삼켜도 바깥은 commit하지 않는다."""
    outer = context.get(type_=OuterUseCase)
    collector = context.get(type_=AggregateCollector)

    with pytest.raises(TransactionRollbackOnlyError):
        await outer.gather_swallow_joined_failure_async()

    assert context.get(type_=AsyncRecordingTransaction).events == [
        "open:1",
        "rollback:1",
        "close:1",
    ]
    assert collector.drain_committed() == []
