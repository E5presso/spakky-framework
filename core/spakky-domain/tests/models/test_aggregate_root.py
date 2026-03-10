from typing import Self
from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable, mutable

from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent


def test_aggregate_root_add_event() -> None:
    """AggregateRoot에 도메인 이벤트를 추가할 수 있음을 검증한다."""

    @mutable
    class User(AbstractAggregateRoot[UUID]):
        name: str

        def validate(self) -> None:
            return

        @immutable
        class Created(AbstractDomainEvent):
            name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            self: Self = cls(uid=cls.next_id(), name=name)
            self.add_event(self.Created(name=self.name))
            return self

    user: User = User.create(name="John")
    assert len(user.events) == 1
    assert isinstance(user.events[0], User.Created)


def test_aggregate_root_remove_event() -> None:
    """AggregateRoot에서 도메인 이벤트를 제거할 수 있음을 검증한다."""

    @mutable
    class User(AbstractAggregateRoot[UUID]):
        name: str

        def validate(self) -> None:
            return

        @immutable
        class Created(AbstractDomainEvent):
            name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            self: Self = cls(uid=cls.next_id(), name=name)
            self.add_event(self.Created(name=self.name))
            return self

    user: User = User.create(name="John")
    assert len(user.events) == 1
    assert isinstance(user.events[0], User.Created)
    user.remove_event(user.events[0])
    assert len(user.events) == 0


def test_aggregate_root_clear_events() -> None:
    """AggregateRoot의 모든 도메인 이벤트를 초기화할 수 있음을 검증한다."""

    @mutable
    class User(AbstractAggregateRoot[UUID]):
        name: str

        def validate(self) -> None:
            return

        @immutable
        class Created(AbstractDomainEvent):
            name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            self: Self = cls(uid=cls.next_id(), name=name)
            self.add_event(self.Created(name=self.name))
            return self

    user: User = User.create(name="John")
    assert len(user.events) == 1
    assert isinstance(user.events[0], User.Created)
    user.clear_events()
    assert len(user.events) == 0
