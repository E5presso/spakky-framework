from dataclasses import field
from typing import Self
from uuid import UUID, uuid4

import pytest
from spakky.core.common.mutability import mutable

from spakky.domain.error import AbstractDomainValidationError
from spakky.domain.models.entity import (
    AbstractEntity,
    CannotMonkeyPatchEntityError,
)


def test_entity_equals() -> None:
    """동일한 uid를 가진 엔티티가 동등함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=uuid4(), name=name)

    user1: User = User(uid=UUID("12345678-1234-5678-1234-567812345678"), name="John")
    user2: User = User(uid=UUID("12345678-1234-5678-1234-567812345678"), name="Sarah")

    assert user1 == user2


def test_entity_not_equals_with_wrong_type() -> None:
    """다른 타입의 엔티티가 동등하지 않음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    @mutable
    class Class(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user: User = User.create(name="John")
    clazz: Class = Class.create(name="first_class")

    assert user != clazz


def test_entity_not_equals_transient() -> None:
    """새로 생성된 엔티티들이 서로 다른 uid를 가지므로 동등하지 않음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user1: User = User.create(name="John")
    user2: User = User.create(name="John")

    assert user1 != user2


def test_entity_not_equals() -> None:
    """다른 uid를 가진 엔티티가 동등하지 않음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user1: User = User.create(name="John")
    user2: User = User.create(name="John")

    assert user1 != user2


def test_entity_hash() -> None:
    """엔티티의 해시값이 uid의 해시값과 동일함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user: User = User(uid=UUID("12345678-1234-5678-1234-567812345678"), name="John")
    assert hash(user) == hash(UUID("12345678-1234-5678-1234-567812345678"))


def test_entity_prevent_monkey_patching() -> None:
    """엔티티의 메서드를 외부에서 동적으로 변경할 수 없음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def update_name(self, name: str) -> None:
            self.name = name

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user: User = User.create(name="John")
    user.update_name("Sarah")

    assert user.name == "Sarah"
    with pytest.raises(CannotMonkeyPatchEntityError):
        user.update_name = lambda name: print(name)


def test_entity_validation_pass() -> None:
    """엔티티 유효성 검사가 실패하면 AbstractDomainValidationError가 발생함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str
        age: int

        def validate(self) -> None:
            if not len(self.name) < 4:
                raise AbstractDomainValidationError
            if not 0 < self.age and self.age < 100:
                raise AbstractDomainValidationError

        def update_name(self, name: str) -> None:
            self.name = name

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls, name: str, age: int) -> Self:
            return cls(uid=cls.next_id(), name=name, age=age)

    @mutable
    class Class(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            if not len(self.name) < 10:
                raise AbstractDomainValidationError

        def update_name(self, name: str) -> None:
            self.name = name

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls, name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user: User = User.create("Sam", 30)
    clazz: Class = Class.create("Astronomy")
    with pytest.raises(AbstractDomainValidationError):
        user.update_name("John")
        clazz.update_name("Neuro-Science")
    with pytest.raises(AbstractDomainValidationError):
        User.create("Sarah", 10)
    with pytest.raises(AbstractDomainValidationError):
        User.create("Jesus", -1)
    with pytest.raises(AbstractDomainValidationError):
        User.create("Chris", 101)


def test_entity_attribute_will_not_change_if_validation_error_raised() -> None:
    """유효성 검사 실패 시 엔티티의 속성이 변경되지 않음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str
        age: int

        def validate(self) -> None:
            if not len(self.name) < 4:
                raise AbstractDomainValidationError
            if not 0 < self.age and self.age < 100:
                raise AbstractDomainValidationError

        def update_name(self, name: str) -> None:
            self.name = name

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls, name: str, age: int) -> Self:
            return cls(uid=cls.next_id(), name=name, age=age)

    user: User = User.create("Sam", 30)
    with pytest.raises(AbstractDomainValidationError):
        user.update_name("John")
    assert user.name == "Sam"


def test_entity_auto_updates_timestamp_and_version_on_change() -> None:
    """엔티티 변경 시 updated_at과 version이 자동으로 업데이트됨을 검증한다."""
    from datetime import UTC, datetime

    from freezegun import freeze_time

    t1 = datetime(2025, 1, 1, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, tzinfo=UTC)
    t3 = datetime(2025, 1, 3, tzinfo=UTC)

    @mutable
    class User(AbstractEntity[UUID]):
        name: str
        email: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    with freeze_time(t1):
        user = User(uid=uuid4(), name="John", email="john@example.com")
        original_updated_at = user.updated_at
        original_version = user.version

    # Change name - should auto-update metadata
    with freeze_time(t2):
        user.name = "Jane"

    assert user.updated_at > original_updated_at, "updated_at should be newer"
    assert user.version != original_version, "version should change"

    # Change email - should update again
    new_updated_at = user.updated_at
    new_version = user.version

    with freeze_time(t3):
        user.email = "jane@example.com"

    assert user.updated_at > new_updated_at, "updated_at should be newer again"
    assert user.version != new_version, "version should change again"


def test_entity_metadata_fields_do_not_trigger_auto_update() -> None:
    """메타데이터 필드 변경이 재귀적 업데이트를 트리거하지 않음을 검증한다."""
    from datetime import UTC, datetime

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John")
    original_version = user.version

    # Manually setting updated_at should not trigger version change
    custom_time = datetime(2020, 1, 1, tzinfo=UTC)
    user.updated_at = custom_time

    assert user.updated_at == custom_time
    assert user.version == original_version, (
        "version should not change when updating metadata"
    )


def test_entity_auto_update_rollback_on_validation_failure() -> None:
    """유효성 검사 실패 시 updated_at과 version이 롤백됨을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str
        age: int

        def validate(self) -> None:
            if self.age < 0:
                raise AbstractDomainValidationError

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John", age=30)
    original_updated_at = user.updated_at
    original_version = user.version

    # Try to set invalid age - should rollback everything
    with pytest.raises(AbstractDomainValidationError):
        user.age = -1

    assert user.age == 30, "age should be rolled back"
    assert user.updated_at == original_updated_at, "updated_at should be rolled back"
    assert user.version == original_version, "version should be rolled back"


def test_entity_persisted_version_of_new_entity_expect_initial_version() -> None:
    """새로 만든 엔티티의 persisted_version은 생성 시점 version과 같음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John")

    assert user.persisted_version == user.version


def test_entity_persisted_version_after_change_expect_loaded_version_kept() -> None:
    """저장소에서 복원한 엔티티를 변경해도 persisted_version은 복원 시점 version을 유지함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    stored_version = uuid4()
    user = User(uid=uuid4(), version=stored_version, name="John")

    user.name = "Jane"

    assert user.version != stored_version
    assert user.persisted_version == stored_version


def test_entity_mark_persisted_expect_persisted_version_advanced_without_bump() -> None:
    """mark_persisted가 persisted_version을 현재 version으로 옮기고 version·updated_at은 건드리지 않음을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John")
    user.name = "Jane"
    changed_version = user.version
    changed_updated_at = user.updated_at

    user.mark_persisted()

    assert user.persisted_version == changed_version
    assert user.version == changed_version
    assert user.updated_at == changed_updated_at


def test_entity_stored_version_tracking_expect_equality_and_repr_unaffected() -> None:
    """저장 version 추적 상태가 달라도 동등성·해시·repr이 영향받지 않음을 검증한다."""

    @mutable
    class Member(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    uid = uuid4()
    version = uuid4()
    untouched = Member(uid=uid, version=version, name="John")
    changed = Member(uid=uid, version=version, name="John")
    changed.name = "Jane"
    saved = Member(uid=uid, version=version, name="John")
    saved.name = "Jane"
    saved.mark_persisted()

    assert untouched == changed == saved
    assert hash(untouched) == hash(changed) == hash(saved)
    assert "persisted_version" not in repr(saved)


def test_entity_version_assigned_directly_expect_persisted_version_kept() -> None:
    """version을 직접 대입해도 persisted_version은 저장소에서 복원한 version을 유지함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    stored_version = uuid4()
    user = User(uid=uuid4(), version=stored_version, name="John")

    user.version = uuid4()
    user.name = "Jane"

    assert user.persisted_version == stored_version


def test_entity_change_after_mark_persisted_expect_marked_version_kept() -> None:
    """mark_persisted 이후의 변경은 표시 시점의 version을 persisted_version으로 유지함을 검증한다."""

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John")
    user.name = "Jane"
    user.mark_persisted()
    saved_version = user.version

    user.name = "Joan"

    assert user.version != saved_version
    assert user.persisted_version == saved_version


def test_entity_with_own_post_init_expect_persisted_version_follows_version() -> None:
    """__post_init__을 직접 정의해 초기화 훅을 거치지 않는 엔티티도 persisted_version을 제공함을 검증한다."""

    @mutable
    class Membership(AbstractEntity[tuple[UUID, UUID]]):
        user_id: UUID
        group_id: UUID
        uid: tuple[UUID, UUID] = field(init=False)

        def __post_init__(self) -> None:
            self.uid = (self.user_id, self.group_id)

        @classmethod
        def next_id(cls) -> tuple[UUID, UUID]:
            return (uuid4(), uuid4())

    membership = Membership(user_id=uuid4(), group_id=uuid4())

    assert membership.persisted_version == membership.version
