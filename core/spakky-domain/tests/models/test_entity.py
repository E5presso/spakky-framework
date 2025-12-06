import sys
from uuid import UUID, uuid4

import pytest
from spakky.core.common.mutability import mutable

from spakky.domain.error import AbstractDomainValidationError
from spakky.domain.models.entity import (
    AbstractEntity,
    CannotMonkeyPatchEntityError,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


def test_entity_equals() -> None:
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    @mutable
    class Class(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        @classmethod
        def create(cls: type[Self], name: str) -> Self:
            return cls(uid=cls.next_id(), name=name)

    user: User = User(uid=UUID("12345678-1234-5678-1234-567812345678"), name="John")
    assert hash(user) == hash(UUID("12345678-1234-5678-1234-567812345678"))


def test_entity_prevent_monkey_patching() -> None:
    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    """Test that updated_at and version are automatically updated when entity changes."""
    import time

    @mutable
    class User(AbstractEntity[UUID]):
        name: str
        email: str

        def validate(self) -> None:
            return

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

    user = User(uid=uuid4(), name="John", email="john@example.com")
    original_updated_at = user.updated_at
    original_version = user.version

    # Small delay to ensure timestamp difference
    time.sleep(0.01)

    # Change name - should auto-update metadata
    user.name = "Jane"

    assert user.updated_at > original_updated_at, "updated_at should be newer"
    assert user.version != original_version, "version should change"

    # Change email - should update again
    new_updated_at = user.updated_at
    new_version = user.version
    time.sleep(0.01)

    user.email = "jane@example.com"

    assert user.updated_at > new_updated_at, "updated_at should be newer again"
    assert user.version != new_version, "version should change again"


def test_entity_metadata_fields_do_not_trigger_auto_update() -> None:
    """Test that changing metadata fields doesn't trigger recursive updates."""
    from datetime import UTC, datetime

    @mutable
    class User(AbstractEntity[UUID]):
        name: str

        def validate(self) -> None:
            return

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
    """Test that updated_at and version rollback if validation fails."""

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
