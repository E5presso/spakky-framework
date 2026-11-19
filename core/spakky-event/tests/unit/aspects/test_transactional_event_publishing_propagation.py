"""중첩된 @Transactional 호출에서 도메인 이벤트가 실제 commit 뒤에 한 번 발행되는지 검증한다."""

from typing import Self, override
from uuid import UUID, uuid4

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable, mutable
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Propagation,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)
from spakky.data.persistency.error import TransactionRollbackOnlyError
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent, AbstractEvent

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.event_publisher import IAsyncEventPublisher, IEventPublisher


@mutable
class Account(AbstractAggregateRoot[UUID]):
    """이벤트를 남기는 테스트용 aggregate."""

    name: str

    def validate(self) -> None:
        """검증할 불변식이 없다."""

    @immutable
    class Opened(AbstractDomainEvent):
        """계정이 열렸다."""

        name: str

    @classmethod
    def next_id(cls) -> UUID:
        """새 식별자를 만든다."""
        return uuid4()

    @classmethod
    def open(cls, name: str) -> Self:
        """계정을 열고 Opened 이벤트를 남긴다."""
        account = cls(uid=cls.next_id(), name=name)
        account.add_event(cls.Opened(name=name))
        return account


class InnerFailureError(Exception):
    """안쪽 use case에서 올라가는 업무 예외."""


@Pod()
class Ledger:
    """transaction 사건과 이벤트 발행을 한 줄로 기록한다."""

    def __init__(self) -> None:
        self.lines: list[str] = []


@Pod()
class RecordingTransaction(AbstractTransaction):
    """physical transaction 사건을 Ledger에 기록한다."""

    def __init__(self, ledger: Ledger) -> None:
        super().__init__()
        self.ledger = ledger
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
        self.ledger.lines.append(f"commit:{self.stack[-1]}")

    @override
    def rollback(self) -> None:
        self.ledger.lines.append(f"rollback:{self.stack[-1]}")


@Pod()
class AsyncRecordingTransaction(AbstractAsyncTransaction):
    """비동기 physical transaction 사건을 Ledger에 기록한다."""

    def __init__(self, ledger: Ledger) -> None:
        super().__init__()
        self.ledger = ledger
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
        self.ledger.lines.append(f"commit:{self.stack[-1]}")

    @override
    async def rollback(self) -> None:
        self.ledger.lines.append(f"rollback:{self.stack[-1]}")


@Pod()
class LedgerPublisher(IEventPublisher):
    """발행된 이벤트를 Ledger에 기록한다."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    @override
    def publish(self, event: AbstractEvent) -> None:
        assert isinstance(event, Account.Opened)
        self.ledger.lines.append(f"publish:{event.name}")


@Pod()
class AsyncLedgerPublisher(IAsyncEventPublisher):
    """비동기로 발행된 이벤트를 Ledger에 기록한다."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    @override
    async def publish(self, event: AbstractEvent) -> None:
        assert isinstance(event, Account.Opened)
        self.ledger.lines.append(f"publish:{event.name}")


@UseCase()
class InnerUseCase:
    """안쪽에서 계정을 여는 use case."""

    def __init__(self, collector: AggregateCollector) -> None:
        self.collector = collector

    @Transactional()
    def joined(self) -> None:
        self.collector.collect(Account.open("inner"))

    @Transactional()
    def joined_failing(self) -> None:
        self.collector.collect(Account.open("inner"))
        raise InnerFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    def separate(self) -> None:
        self.collector.collect(Account.open("inner"))

    @Transactional()
    async def joined_async(self) -> None:
        self.collector.collect(Account.open("inner"))

    @Transactional()
    async def joined_failing_async(self) -> None:
        self.collector.collect(Account.open("inner"))
        raise InnerFailureError()

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    async def separate_async(self) -> None:
        self.collector.collect(Account.open("inner"))


@UseCase()
class OuterUseCase:
    """안쪽 use case를 부르는 바깥 use case."""

    def __init__(self, inner: InnerUseCase, collector: AggregateCollector) -> None:
        self.inner = inner
        self.collector = collector

    @Transactional()
    def call_joined(self) -> None:
        self.collector.collect(Account.open("outer"))
        self.inner.joined()

    @Transactional()
    def swallow_joined_failure(self) -> None:
        self.collector.collect(Account.open("outer"))
        try:
            self.inner.joined_failing()
        except InnerFailureError:
            return

    @Transactional()
    def call_separate(self) -> None:
        self.collector.collect(Account.open("outer"))
        self.inner.separate()

    @Transactional()
    async def call_joined_async(self) -> None:
        self.collector.collect(Account.open("outer"))
        await self.inner.joined_async()

    @Transactional()
    async def swallow_joined_failure_async(self) -> None:
        self.collector.collect(Account.open("outer"))
        try:
            await self.inner.joined_failing_async()
        except InnerFailureError:
            return

    @Transactional()
    async def call_separate_async(self) -> None:
        self.collector.collect(Account.open("outer"))
        await self.inner.separate_async()


@pytest.fixture(name="context")
def context_fixture() -> ApplicationContext:
    """transaction·이벤트 발행 aspect를 양쪽 모두 올린 컨텍스트."""
    context = ApplicationContext()
    context.add(Ledger)
    context.add(RecordingTransaction)
    context.add(AsyncRecordingTransaction)
    context.add(LedgerPublisher)
    context.add(AsyncLedgerPublisher)
    context.add(AggregateCollector)
    context.add(TransactionSynchronization)
    context.add(InnerUseCase)
    context.add(OuterUseCase)
    context.add(TransactionalAspect)
    context.add(AsyncTransactionalAspect)
    context.add(TransactionalEventPublishingAspect)
    context.add(AsyncTransactionalEventPublishingAspect)
    context.start()
    return context


def test_joined_call_expect_events_published_once_after_outer_commit(
    context: ApplicationContext,
) -> None:
    """합쳐진 안쪽의 이벤트는 안쪽이 끝날 때가 아니라 바깥 commit 뒤에 한 번 발행된다."""
    context.get(type_=OuterUseCase).call_joined()

    assert context.get(type_=Ledger).lines == [
        "commit:1",
        "publish:outer",
        "publish:inner",
    ]


def test_joined_failure_swallowed_expect_rollback_and_no_events(
    context: ApplicationContext,
) -> None:
    """rollback만 가능한 transaction은 어떤 이벤트도 발행하지 않는다."""
    with pytest.raises(TransactionRollbackOnlyError):
        context.get(type_=OuterUseCase).swallow_joined_failure()

    assert context.get(type_=Ledger).lines == ["rollback:1"]


def test_requires_new_call_expect_inner_events_after_inner_commit(
    context: ApplicationContext,
) -> None:
    """REQUIRES_NEW 안쪽의 이벤트는 안쪽 commit 직후, 바깥 이벤트는 바깥 commit 뒤에 발행된다."""
    context.get(type_=OuterUseCase).call_separate()

    assert context.get(type_=Ledger).lines == [
        "commit:2",
        "publish:inner",
        "commit:1",
        "publish:outer",
    ]


async def test_async_joined_call_expect_events_published_once_after_outer_commit(
    context: ApplicationContext,
) -> None:
    """비동기 합쳐진 안쪽의 이벤트도 바깥 commit 뒤에 한 번 발행된다."""
    await context.get(type_=OuterUseCase).call_joined_async()

    assert context.get(type_=Ledger).lines == [
        "commit:1",
        "publish:outer",
        "publish:inner",
    ]


async def test_async_joined_failure_swallowed_expect_rollback_and_no_events(
    context: ApplicationContext,
) -> None:
    """비동기 rollback만 가능한 transaction도 이벤트를 발행하지 않는다."""
    with pytest.raises(TransactionRollbackOnlyError):
        await context.get(type_=OuterUseCase).swallow_joined_failure_async()

    assert context.get(type_=Ledger).lines == ["rollback:1"]


async def test_async_requires_new_call_expect_inner_events_after_inner_commit(
    context: ApplicationContext,
) -> None:
    """비동기 REQUIRES_NEW 안쪽의 이벤트는 안쪽 commit 직후에 발행된다."""
    await context.get(type_=OuterUseCase).call_separate_async()

    assert context.get(type_=Ledger).lines == [
        "commit:2",
        "publish:inner",
        "commit:1",
        "publish:outer",
    ]
