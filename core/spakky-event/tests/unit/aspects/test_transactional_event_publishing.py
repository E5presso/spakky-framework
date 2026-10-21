from typing import Self
from uuid import UUID, uuid4

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable, mutable
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector
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
from spakky.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)


@mutable
class User(AbstractAggregateRoot[UUID]):
    """User aggregate root."""

    username: str

    def validate(self) -> None:
        """Validate user."""
        pass

    @immutable
    class Created(AbstractDomainEvent):
        """Domain event raised when a user is created."""

        user_id: str
        username: str

    @classmethod
    def next_id(cls) -> UUID:
        """Generate next user ID."""
        return uuid4()

    @classmethod
    def create(cls: type[Self], username: str) -> Self:
        """Create a new user and raise Created event."""
        user: Self = cls(uid=cls.next_id(), username=username)
        user.add_event(cls.Created(user_id=str(user.uid), username=username))
        return user


def test_sync_aspect_publishes_events_on_success() -> None:
    """TransactionalEventPublishingAspect가 성공적인 실행 후 이벤트를 발행함을 검증한다."""

    @Pod()
    class InMemoryTransaction(AbstractTransaction):
        def initialize(self) -> None: ...
        def dispose(self) -> None: ...
        def commit(self) -> None: ...
        def rollback(self) -> None: ...

    @Pod()
    class InMemoryDomainEventPublisher(IEventPublisher):
        published_events: list[AbstractEvent] = []

        def publish(self, event: AbstractEvent) -> None:
            self.published_events.append(event)

    @UseCase()
    class CreateUserUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        def execute(self, username: str) -> User:
            user = User.create(username)
            self.collector.collect(user)
            return user

    context = ApplicationContext()
    context.add(InMemoryTransaction)
    context.add(InMemoryDomainEventPublisher)
    context.add(AggregateCollector)
    context.add(CreateUserUseCase)
    context.add(TransactionalAspect)
    context.add(TransactionalEventPublishingAspect)
    context.start()

    use_case: CreateUserUseCase = context.get(type_=CreateUserUseCase)
    publisher: InMemoryDomainEventPublisher = context.get(
        type_=InMemoryDomainEventPublisher
    )
    collector: AggregateCollector = context.get(type_=AggregateCollector)

    result = use_case.execute("alice")

    assert result.username == "alice"
    assert len(publisher.published_events) == 1
    assert isinstance(publisher.published_events[0], User.Created)
    assert publisher.published_events[0].username == "alice"
    assert len(result.events) == 0  # Events should be cleared
    assert len(collector.all()) == 0  # Collector should be cleared


def test_sync_aspect_does_not_publish_on_error() -> None:
    """TransactionalEventPublishingAspect가 메서드 실패 시 이벤트를 발행하지 않음을 검증한다."""

    @Pod()
    class InMemoryTransaction(AbstractTransaction):
        def initialize(self) -> None: ...
        def dispose(self) -> None: ...
        def commit(self) -> None: ...
        def rollback(self) -> None: ...

    @Pod()
    class InMemoryDomainEventPublisher(IEventPublisher):
        published_events: list[AbstractEvent] = []

        def publish(self, event: AbstractEvent) -> None:
            self.published_events.append(event)

    @UseCase()
    class CreateUserUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        def execute(self, username: str) -> User:
            user = User.create(username)
            self.collector.collect(user)
            raise RuntimeError("Something went wrong")

    context = ApplicationContext()
    context.add(InMemoryTransaction)
    context.add(InMemoryDomainEventPublisher)
    context.add(AggregateCollector)
    context.add(CreateUserUseCase)
    context.add(TransactionalAspect)
    context.add(TransactionalEventPublishingAspect)
    context.start()

    use_case: CreateUserUseCase = context.get(type_=CreateUserUseCase)
    publisher: InMemoryDomainEventPublisher = context.get(
        type_=InMemoryDomainEventPublisher
    )
    collector: AggregateCollector = context.get(type_=AggregateCollector)

    with pytest.raises(RuntimeError, match="Something went wrong"):
        use_case.execute("alice")

    assert len(publisher.published_events) == 0  # No events should be published
    assert len(collector.all()) == 0  # Collector should be cleared


@pytest.mark.asyncio
async def test_async_aspect_publishes_events_on_success() -> None:
    """AsyncTransactionalEventPublishingAspect가 성공적인 실행 후 이벤트를 발행함을 검증한다."""

    @Pod()
    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        async def initialize(self) -> None: ...
        async def dispose(self) -> None: ...
        async def commit(self) -> None: ...
        async def rollback(self) -> None: ...

    @Pod()
    class AsyncInMemoryDomainEventPublisher(IAsyncEventPublisher):
        published_events: list[AbstractEvent] = []

        async def publish(self, event: AbstractEvent) -> None:
            self.published_events.append(event)

    @UseCase()
    class CreateUserUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        async def execute(self, username: str) -> User:
            user = User.create(username)
            self.collector.collect(user)
            return user

    context = ApplicationContext()
    context.add(AsyncInMemoryTransaction)
    context.add(AsyncInMemoryDomainEventPublisher)
    context.add(AggregateCollector)
    context.add(CreateUserUseCase)
    context.add(AsyncTransactionalAspect)
    context.add(AsyncTransactionalEventPublishingAspect)
    context.start()

    use_case: CreateUserUseCase = context.get(type_=CreateUserUseCase)
    publisher: AsyncInMemoryDomainEventPublisher = context.get(
        type_=AsyncInMemoryDomainEventPublisher
    )
    collector: AggregateCollector = context.get(type_=AggregateCollector)

    result = await use_case.execute("alice")

    assert result.username == "alice"
    assert len(publisher.published_events) == 1
    assert isinstance(publisher.published_events[0], User.Created)
    assert publisher.published_events[0].username == "alice"
    assert len(result.events) == 0  # Events should be cleared
    assert len(collector.all()) == 0  # Collector should be cleared


@pytest.mark.asyncio
async def test_async_aspect_does_not_publish_on_error() -> None:
    """AsyncTransactionalEventPublishingAspect가 메서드 실패 시 이벤트를 발행하지 않음을 검증한다."""

    @Pod()
    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        async def initialize(self) -> None: ...
        async def dispose(self) -> None: ...
        async def commit(self) -> None: ...
        async def rollback(self) -> None: ...

    @Pod()
    class AsyncInMemoryDomainEventPublisher(IAsyncEventPublisher):
        published_events: list[AbstractEvent] = []

        async def publish(self, event: AbstractEvent) -> None:
            self.published_events.append(event)

    @UseCase()
    class CreateUserUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        async def execute(self, username: str) -> User:
            user = User.create(username)
            self.collector.collect(user)
            raise RuntimeError("Something went wrong")

    context = ApplicationContext()
    context.add(AsyncInMemoryTransaction)
    context.add(AsyncInMemoryDomainEventPublisher)
    context.add(AggregateCollector)
    context.add(CreateUserUseCase)
    context.add(AsyncTransactionalAspect)
    context.add(AsyncTransactionalEventPublishingAspect)
    context.start()

    use_case: CreateUserUseCase = context.get(type_=CreateUserUseCase)
    publisher: AsyncInMemoryDomainEventPublisher = context.get(
        type_=AsyncInMemoryDomainEventPublisher
    )
    collector: AggregateCollector = context.get(type_=AggregateCollector)

    with pytest.raises(RuntimeError, match="Something went wrong"):
        await use_case.execute("alice")

    assert len(publisher.published_events) == 0  # No events should be published
    assert len(collector.all()) == 0  # Collector should be cleared


@pytest.mark.asyncio
async def test_async_aspect_publishes_multiple_events_from_multiple_aggregates() -> (
    None
):
    """여러 aggregate에서 발생한 모든 이벤트를 발행함을 검증한다."""

    @Pod()
    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        async def initialize(self) -> None: ...
        async def dispose(self) -> None: ...
        async def commit(self) -> None: ...
        async def rollback(self) -> None: ...

    @Pod()
    class AsyncInMemoryDomainEventPublisher(IAsyncEventPublisher):
        published_events: list[AbstractEvent] = []

        async def publish(self, event: AbstractEvent) -> None:
            self.published_events.append(event)

    @UseCase()
    class CreateMultipleUsersUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        async def execute(self) -> list[User]:
            user1 = User.create("alice")
            user2 = User.create("bob")
            self.collector.collect(user1)
            self.collector.collect(user2)
            return [user1, user2]

    context = ApplicationContext()
    context.add(AsyncInMemoryTransaction)
    context.add(AsyncInMemoryDomainEventPublisher)
    context.add(AggregateCollector)
    context.add(CreateMultipleUsersUseCase)
    context.add(AsyncTransactionalAspect)
    context.add(AsyncTransactionalEventPublishingAspect)
    context.start()

    use_case: CreateMultipleUsersUseCase = context.get(type_=CreateMultipleUsersUseCase)
    publisher: AsyncInMemoryDomainEventPublisher = context.get(
        type_=AsyncInMemoryDomainEventPublisher
    )
    collector: AggregateCollector = context.get(type_=AggregateCollector)

    results = await use_case.execute()

    assert len(results) == 2
    assert len(publisher.published_events) == 2
    assert all(isinstance(e, User.Created) for e in publisher.published_events)
    event1 = publisher.published_events[0]
    event2 = publisher.published_events[1]
    assert isinstance(event1, User.Created)
    assert isinstance(event2, User.Created)
    assert event1.username == "alice"
    assert event2.username == "bob"
    assert all(len(user.events) == 0 for user in results)  # All events cleared
    assert len(collector.all()) == 0  # Collector cleared


def test_followup_transaction_does_not_republish_parent_events() -> None:
    """핸들러의 후속 트랜잭션은 이미 발행 중인 부모 이벤트를 다시 수집하지 않는다."""
    collector = AggregateCollector()
    observed = []

    class Publisher(IEventPublisher):
        def publish(self, event: AbstractEvent) -> None:
            assert isinstance(event, User.Created)
            observed.append(event.username)
            if event.username == "parent":
                collector.collect(User.create("child"))
                aspect.after_returning(None)

    aspect = TransactionalEventPublishingAspect(collector, Publisher())
    parent = User.create("parent")
    collector.collect(parent)
    collector.collect(parent)
    aspect.after_returning(None)
    assert observed == ["parent", "child"]
    assert collector.all() == []
    assert parent.events == []


@pytest.mark.asyncio
async def test_async_followup_transaction_does_not_republish_parent_events() -> None:
    """비동기 후속 트랜잭션도 부모 이벤트를 중복 발행하지 않는다."""
    collector = AggregateCollector()
    observed = []

    class Publisher(IAsyncEventPublisher):
        async def publish(self, event: AbstractEvent) -> None:
            assert isinstance(event, User.Created)
            observed.append(event.username)
            if event.username == "parent":
                collector.collect(User.create("child"))
                await aspect.after_returning_async(None)

    aspect = AsyncTransactionalEventPublishingAspect(collector, Publisher())
    parent = User.create("parent")
    collector.collect(parent)
    collector.collect(parent)
    await aspect.after_returning_async(None)
    assert observed == ["parent", "child"]
    assert collector.all() == []
    assert parent.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_commit", [False, True])
async def test_events_are_published_after_commit_and_disposal(
    fail_commit: bool,
) -> None:
    """후속 핸들러를 실행하기 전에 최초 트랜잭션의 commit과 dispose를 끝낸다."""
    observed = []

    @Pod()
    class Transaction(AbstractAsyncTransaction):
        async def initialize(self) -> None:
            observed.append("open")

        async def dispose(self) -> None:
            observed.append("dispose")

        async def commit(self) -> None:
            observed.append("commit")
            if fail_commit:
                raise RuntimeError("commit failed")

        async def rollback(self) -> None:
            observed.append("rollback")

    @Pod()
    class Publisher(IAsyncEventPublisher):
        async def publish(self, event: AbstractEvent) -> None:
            observed.append("event")

    @UseCase()
    class CreateUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        async def run(self) -> None:
            self.collector.collect(User.create("parent"))

    context = ApplicationContext()
    for component in (
        Transaction,
        Publisher,
        CreateUseCase,
        AggregateCollector,
        AsyncTransactionalAspect,
        AsyncTransactionalEventPublishingAspect,
    ):
        context.add(component)
    context.start()
    try:
        if fail_commit:
            with pytest.raises(RuntimeError, match="commit failed"):
                await context.get(CreateUseCase).run()
        else:
            await context.get(CreateUseCase).run()
    finally:
        context.stop()
    assert observed == (
        ["open", "commit", "rollback", "dispose"]
        if fail_commit
        else ["open", "commit", "dispose", "event"]
    )


@pytest.mark.parametrize("fail_commit", [False, True])
def test_sync_events_are_published_after_commit_and_disposal(
    fail_commit: bool,
) -> None:
    """후속 핸들러를 실행하기 전에 최초 트랜잭션의 commit과 dispose를 끝낸다."""
    observed = []

    @Pod()
    class Transaction(AbstractTransaction):
        def initialize(self) -> None:
            observed.append("open")

        def dispose(self) -> None:
            observed.append("dispose")

        def commit(self) -> None:
            observed.append("commit")
            if fail_commit:
                raise RuntimeError("commit failed")

        def rollback(self) -> None:
            observed.append("rollback")

    @Pod()
    class Publisher(IEventPublisher):
        def publish(self, event: AbstractEvent) -> None:
            observed.append("event")

    @UseCase()
    class CreateUseCase:
        def __init__(self, collector: AggregateCollector) -> None:
            self.collector = collector

        @Transactional()
        def run(self) -> None:
            self.collector.collect(User.create("parent"))

    context = ApplicationContext()
    for component in (
        Transaction,
        Publisher,
        CreateUseCase,
        AggregateCollector,
        TransactionalAspect,
        TransactionalEventPublishingAspect,
    ):
        context.add(component)
    context.start()
    try:
        if fail_commit:
            with pytest.raises(RuntimeError, match="commit failed"):
                context.get(CreateUseCase).run()
        else:
            context.get(CreateUseCase).run()
    finally:
        context.stop()
    assert observed == (
        ["open", "commit", "rollback", "dispose"]
        if fail_commit
        else ["open", "commit", "dispose", "event"]
    )
