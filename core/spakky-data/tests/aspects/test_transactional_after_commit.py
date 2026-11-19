"""@Transactional이 실제로 commit한 뒤에만 after-commit 작업을 돌리는지 검증한다."""

import asyncio
import logging
from typing import override

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase

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
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)


class BusinessFailureError(Exception):
    """use case에서 올라가는 업무 예외."""


class CallbackFailureError(Exception):
    """after-commit 작업에서 나는 예외."""


@Pod()
class Journal:
    """transaction 사건과 after-commit 작업을 한 줄로 기록한다."""

    def __init__(self) -> None:
        self.lines: list[str] = []


@Pod()
class RecordingTransaction(AbstractTransaction):
    """physical transaction의 commit·rollback을 번호와 함께 기록한다."""

    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.journal = journal
        self.opened = 0
        self.stack: list[int] = []

    @override
    def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)

    @override
    def dispose(self) -> None:
        self.stack.pop()

    @override
    def commit(self) -> None:
        self.journal.lines.append(f"commit:{self.stack[-1]}")

    @override
    def rollback(self) -> None:
        self.journal.lines.append(f"rollback:{self.stack[-1]}")


@Pod()
class AsyncRecordingTransaction(AbstractAsyncTransaction):
    """비동기 physical transaction의 commit·rollback을 번호와 함께 기록한다."""

    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.journal = journal
        self.opened = 0
        self.stack: list[int] = []

    @override
    async def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)

    @override
    async def dispose(self) -> None:
        self.stack.pop()

    @override
    async def commit(self) -> None:
        self.journal.lines.append(f"commit:{self.stack[-1]}")

    @override
    async def rollback(self) -> None:
        self.journal.lines.append(f"rollback:{self.stack[-1]}")


@UseCase()
class InnerUseCase:
    """안쪽에서 after-commit 작업을 거는 use case."""

    def __init__(
        self, journal: Journal, synchronization: TransactionSynchronization
    ) -> None:
        self.journal = journal
        self.synchronization = synchronization

    def _after(self, label: str) -> None:
        self.synchronization.register_after_commit(
            lambda: self.journal.lines.append(f"after:{label}")
        )

    @Transactional()
    def joined(self) -> None:
        self._after("inner")
        self.journal.lines.append("inner-returned")

    @Transactional()
    def joined_failing(self) -> None:
        self._after("inner")
        raise BusinessFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def separate(self) -> None:
        self._after("inner")

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def separate_failing(self) -> None:
        self._after("inner")
        raise BusinessFailureError()

    @Transactional()
    async def joined_async(self) -> None:
        self._after("inner")
        self.journal.lines.append("inner-returned")

    @Transactional()
    async def joined_failing_async(self) -> None:
        self._after("inner")
        raise BusinessFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def separate_async(self) -> None:
        self._after("inner")

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def separate_failing_async(self) -> None:
        self._after("inner")
        raise BusinessFailureError()


@UseCase()
class OuterUseCase:
    """after-commit 작업을 걸고 안쪽 use case를 부르는 바깥 use case."""

    def __init__(
        self,
        inner: InnerUseCase,
        journal: Journal,
        synchronization: TransactionSynchronization,
    ) -> None:
        self.inner = inner
        self.journal = journal
        self.synchronization = synchronization

    def _after(self, label: str) -> None:
        self.synchronization.register_after_commit(
            lambda: self.journal.lines.append(f"after:{label}")
        )

    @Transactional()
    def alone(self) -> str:
        self._after("outer")
        return "done"

    @Transactional()
    def failing(self) -> None:
        self._after("outer")
        raise BusinessFailureError()

    @Transactional()
    def with_failing_callback(self) -> str:
        self.synchronization.register_after_commit(self._raise_callback_failure)
        self._after("outer")
        return "done"

    def _raise_callback_failure(self) -> None:
        raise CallbackFailureError()

    @Transactional()
    def call_joined(self) -> None:
        self._after("outer")
        self.inner.joined()

    @Transactional()
    def swallow_joined_failure(self) -> None:
        try:
            self.inner.joined_failing()
        except BusinessFailureError:
            return

    @Transactional()
    def call_separate(self) -> None:
        self._after("outer")
        self.inner.separate()

    @Transactional()
    def swallow_separate_failure(self) -> None:
        self._after("outer")
        try:
            self.inner.separate_failing()
        except BusinessFailureError:
            return

    @Transactional()
    async def alone_async(self) -> str:
        self._after("outer")
        return "done"

    @Transactional()
    async def failing_async(self) -> None:
        self._after("outer")
        raise BusinessFailureError()

    @Transactional()
    async def call_joined_async(self) -> None:
        self._after("outer")
        await self.inner.joined_async()

    @Transactional()
    async def swallow_joined_failure_async(self) -> None:
        try:
            await self.inner.joined_failing_async()
        except BusinessFailureError:
            return

    @Transactional()
    async def call_separate_async(self) -> None:
        self._after("outer")
        await self.inner.separate_async()

    @Transactional()
    async def swallow_separate_failure_async(self) -> None:
        self._after("outer")
        try:
            await self.inner.separate_failing_async()
        except BusinessFailureError:
            return

    @Transactional()
    async def spawn_late_child_async(
        self, release: asyncio.Event
    ) -> asyncio.Task[None]:
        """Start a fire-and-forget child that runs only after this call commits."""
        self._after("outer")

        async def child() -> None:
            await release.wait()
            await self.inner.joined_async()

        return asyncio.create_task(child())


@pytest.fixture(name="context")
def context_fixture() -> ApplicationContext:
    """기록용 transaction, synchronization, 양쪽 aspect를 올린 컨텍스트."""
    context = ApplicationContext()
    for pod in (
        Journal,
        RecordingTransaction,
        AsyncRecordingTransaction,
        AggregateCollector,
        TransactionSynchronization,
        InnerUseCase,
        OuterUseCase,
        TransactionalAspect,
        AsyncTransactionalAspect,
    ):
        context.add(pod)
    context.start()
    return context


def test_after_commit_single_transaction_expect_runs_after_commit(
    context: ApplicationContext,
) -> None:
    """commit이 끝난 뒤에 after-commit 작업이 한 번 돈다."""
    result = context.get(type_=OuterUseCase).alone()

    assert result == "done"
    assert context.get(type_=Journal).lines == ["commit:1", "after:outer"]


def test_after_commit_rollback_expect_not_run(context: ApplicationContext) -> None:
    """rollback된 transaction의 after-commit 작업은 돌지 않는다."""
    with pytest.raises(BusinessFailureError):
        context.get(type_=OuterUseCase).failing()

    assert context.get(type_=Journal).lines == ["rollback:1"]
    assert not context.get(type_=TransactionSynchronization).is_active


def test_after_commit_joined_inner_expect_runs_after_outer_commit_only(
    context: ApplicationContext,
) -> None:
    """합쳐진 안쪽이 건 작업은 안쪽이 끝날 때가 아니라 가장 바깥 commit 뒤에 돈다."""
    context.get(type_=OuterUseCase).call_joined()

    assert context.get(type_=Journal).lines == [
        "inner-returned",
        "commit:1",
        "after:outer",
        "after:inner",
    ]


def test_after_commit_joined_failure_swallowed_expect_not_run(
    context: ApplicationContext,
) -> None:
    """rollback-only로 끝난 transaction의 after-commit 작업은 돌지 않는다."""
    with pytest.raises(TransactionRollbackOnlyError):
        context.get(type_=OuterUseCase).swallow_joined_failure()

    assert context.get(type_=Journal).lines == ["rollback:1"]


def test_after_commit_requires_new_expect_inner_runs_after_inner_commit(
    context: ApplicationContext,
) -> None:
    """REQUIRES_NEW 안쪽의 작업은 안쪽 commit 직후, 바깥 commit 전에 돈다."""
    context.get(type_=OuterUseCase).call_separate()

    assert context.get(type_=Journal).lines == [
        "commit:2",
        "after:inner",
        "commit:1",
        "after:outer",
    ]


def test_after_commit_requires_new_failure_expect_only_outer_runs(
    context: ApplicationContext,
) -> None:
    """rollback된 REQUIRES_NEW 안쪽의 작업은 버려지고 바깥 작업만 돈다."""
    context.get(type_=OuterUseCase).swallow_separate_failure()

    assert context.get(type_=Journal).lines == [
        "rollback:2",
        "commit:1",
        "after:outer",
    ]


def test_after_commit_failing_callback_expect_logged_and_rest_run(
    context: ApplicationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """after-commit 작업 하나가 실패해도 호출은 성공하고 나머지 작업이 돈다."""
    with caplog.at_level(logging.ERROR):
        result = context.get(type_=OuterUseCase).with_failing_callback()

    assert result == "done"
    assert context.get(type_=Journal).lines == ["commit:1", "after:outer"]
    assert "After-commit callback" in caplog.text


async def test_async_after_commit_single_transaction_expect_runs_after_commit(
    context: ApplicationContext,
) -> None:
    """비동기 commit이 끝난 뒤에 after-commit 작업이 한 번 돈다."""
    result = await context.get(type_=OuterUseCase).alone_async()

    assert result == "done"
    assert context.get(type_=Journal).lines == ["commit:1", "after:outer"]


async def test_async_after_commit_rollback_expect_not_run(
    context: ApplicationContext,
) -> None:
    """비동기 rollback된 transaction의 after-commit 작업은 돌지 않는다."""
    with pytest.raises(BusinessFailureError):
        await context.get(type_=OuterUseCase).failing_async()

    assert context.get(type_=Journal).lines == ["rollback:1"]


async def test_async_after_commit_joined_inner_expect_runs_after_outer_commit_only(
    context: ApplicationContext,
) -> None:
    """비동기 합쳐진 안쪽의 작업도 가장 바깥 commit 뒤에 돈다."""
    await context.get(type_=OuterUseCase).call_joined_async()

    assert context.get(type_=Journal).lines == [
        "inner-returned",
        "commit:1",
        "after:outer",
        "after:inner",
    ]


async def test_async_after_commit_joined_failure_swallowed_expect_not_run(
    context: ApplicationContext,
) -> None:
    """비동기 rollback-only로 끝난 transaction의 작업은 돌지 않는다."""
    with pytest.raises(TransactionRollbackOnlyError):
        await context.get(type_=OuterUseCase).swallow_joined_failure_async()

    assert context.get(type_=Journal).lines == ["rollback:1"]


async def test_async_after_commit_requires_new_expect_inner_runs_after_inner_commit(
    context: ApplicationContext,
) -> None:
    """비동기 REQUIRES_NEW 안쪽의 작업은 안쪽 commit 직후에 돈다."""
    await context.get(type_=OuterUseCase).call_separate_async()

    assert context.get(type_=Journal).lines == [
        "commit:2",
        "after:inner",
        "commit:1",
        "after:outer",
    ]


async def test_async_after_commit_requires_new_failure_expect_only_outer_runs(
    context: ApplicationContext,
) -> None:
    """비동기 rollback된 REQUIRES_NEW 안쪽의 작업은 버려진다."""
    await context.get(type_=OuterUseCase).swallow_separate_failure_async()

    assert context.get(type_=Journal).lines == [
        "rollback:2",
        "commit:1",
        "after:outer",
    ]


async def test_async_after_commit_fire_and_forget_child_expect_own_commit_runs_its_work(
    context: ApplicationContext,
) -> None:
    """바깥이 commit한 뒤 도는 자식의 작업은 닫힌 frame에 붙지 않고 자기 commit 뒤에 돈다."""
    release = asyncio.Event()

    task = await context.get(type_=OuterUseCase).spawn_late_child_async(release)
    assert context.get(type_=Journal).lines == ["commit:1", "after:outer"]
    release.set()
    await task

    assert context.get(type_=Journal).lines == [
        "commit:1",
        "after:outer",
        "inner-returned",
        "commit:2",
        "after:inner",
    ]


@Pod()
class NoAutocommitTransaction(AbstractTransaction):
    """autocommit=False라 commit하지 않는 transaction."""

    def __init__(self, journal: Journal) -> None:
        super().__init__(autocommit=False)
        self.journal = journal

    @override
    def initialize(self) -> None:
        return

    @override
    def dispose(self) -> None:
        self.journal.lines.append("dispose")

    @override
    def commit(self) -> None:
        self.journal.lines.append("commit")

    @override
    def rollback(self) -> None:
        self.journal.lines.append("rollback")


@Pod()
class AsyncNoAutocommitTransaction(AbstractAsyncTransaction):
    """autocommit=False라 commit하지 않는 비동기 transaction."""

    def __init__(self, journal: Journal) -> None:
        super().__init__(autocommit=False)
        self.journal = journal

    @override
    async def initialize(self) -> None:
        return

    @override
    async def dispose(self) -> None:
        self.journal.lines.append("dispose")

    @override
    async def commit(self) -> None:
        self.journal.lines.append("commit")

    @override
    async def rollback(self) -> None:
        self.journal.lines.append("rollback")


@UseCase()
class NoAutocommitUseCase:
    """autocommit=False transaction 안에서 after-commit 작업을 건다."""

    def __init__(
        self, journal: Journal, synchronization: TransactionSynchronization
    ) -> None:
        self.journal = journal
        self.synchronization = synchronization

    @Transactional()
    def run(self) -> None:
        self.synchronization.register_after_commit(
            lambda: self.journal.lines.append("after")
        )

    @Transactional()
    async def run_async(self) -> None:
        self.synchronization.register_after_commit(
            lambda: self.journal.lines.append("after")
        )


@pytest.fixture(name="no_autocommit_context")
def no_autocommit_context_fixture() -> ApplicationContext:
    """autocommit=False transaction을 올린 컨텍스트."""
    context = ApplicationContext()
    for pod in (
        Journal,
        NoAutocommitTransaction,
        AsyncNoAutocommitTransaction,
        AggregateCollector,
        TransactionSynchronization,
        NoAutocommitUseCase,
        TransactionalAspect,
        AsyncTransactionalAspect,
    ):
        context.add(pod)
    context.start()
    return context


def test_after_commit_autocommit_disabled_expect_not_run(
    no_autocommit_context: ApplicationContext,
) -> None:
    """autocommit=False라 commit하지 않았으면 after-commit 작업은 돌지 않는다."""
    no_autocommit_context.get(type_=NoAutocommitUseCase).run()

    assert no_autocommit_context.get(type_=Journal).lines == ["dispose"]
    assert (
        no_autocommit_context.get(type_=TransactionSynchronization).is_active is False
    )


async def test_async_after_commit_autocommit_disabled_expect_not_run(
    no_autocommit_context: ApplicationContext,
) -> None:
    """비동기에서도 commit하지 않았으면 after-commit 작업은 돌지 않는다."""
    await no_autocommit_context.get(type_=NoAutocommitUseCase).run_async()

    assert no_autocommit_context.get(type_=Journal).lines == ["dispose"]
