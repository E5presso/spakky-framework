from datetime import datetime
from typing import Callable, Self
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.pod.annotations.tag import Tag
from spakky.core.pod.interfaces.tag_registry import ITagRegistry
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from sqlalchemy import DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.schema_registry import (
    NoSchemaFoundFromDomainError,
    SchemaRegistry,
)
from spakky.plugins.sqlalchemy.orm.table import (
    AbstractMappableTable,
    AbstractTable,
    Table,
)

# --- In-Memory ITagRegistry fixture implementation ---


class InMemoryTagRegistry(ITagRegistry):
    """In-memory implementation of ITagRegistry for testing."""

    _tags: set[Tag]

    def __init__(self) -> None:
        self._tags = set()

    @property
    def tags(self) -> frozenset[Tag]:
        return frozenset(self._tags)

    def register_tag(self, tag: Tag) -> None:
        self._tags.add(tag)

    def contains_tag(self, tag: Tag) -> bool:
        return tag in self._tags

    def list_tags(
        self, selector: Callable[[Tag], bool] | None = None
    ) -> frozenset[Tag]:
        if selector is None:
            return frozenset(self._tags)
        return frozenset(tag for tag in self._tags if selector(tag))


# --- Domain and Table fixtures ---


@mutable
class User(AbstractAggregateRoot[UUID]):
    """Test domain entity."""

    username: str
    password: str

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()

    def validate(self) -> None:
        return


@Table(User)
class UserTable(AbstractMappableTable[User]):
    """Test table for User domain."""

    __tablename__ = "test_users"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    username: Mapped[str] = mapped_column(String(), nullable=False)
    password: Mapped[str] = mapped_column(String(), nullable=False)

    @classmethod
    def from_domain(cls, domain: User) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            username=domain.username,
            password=domain.password,
        )

    def to_domain(self) -> User:
        return User(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            username=self.username,
            password=self.password,
        )


@pytest.fixture
def tag_registry() -> InMemoryTagRegistry:
    """Fixture for in-memory tag registry."""
    return InMemoryTagRegistry()


@pytest.fixture
def tag_registry_with_user_table() -> InMemoryTagRegistry:
    """Fixture for tag registry with UserTable registered."""
    registry = InMemoryTagRegistry()
    registry.register_tag(Table.get(UserTable))
    return registry


# --- SchemaRegistry tests ---


def test_schema_registry_init_expect_no_registered_schemas(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """SchemaRegistry 초기화 시 등록된 스키마가 없음을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    # No schema should be found since no tables were registered
    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.from_domain(user)


def test_set_tag_registry_with_table_tags_expect_domain_convertible(
    tag_registry_with_user_table: InMemoryTagRegistry,
) -> None:
    """set_tag_registry로 Table 태그 등록 시 도메인-테이블 변환이 가능함을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry_with_user_table)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    result = registry.from_domain(user)

    assert isinstance(result, UserTable)
    assert result.uid == user.uid


def test_set_tag_registry_with_empty_registry_expect_no_conversion(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """빈 tag registry로 set_tag_registry 호출 시 도메인 변환이 불가능함을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.from_domain(user)


def test_set_tag_registry_with_non_table_tags_expect_ignored(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """Table이 아닌 태그는 등록 과정에서 무시됨을 검증한다."""
    registry = SchemaRegistry()
    # Register a non-Table tag
    non_table_tag = Tag()
    tag_registry.register_tag(non_table_tag)
    registry.set_tag_registry(tag_registry)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    # Non-Table tags should be ignored, so no schema should be found
    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.from_domain(user)


def test_from_domain_registered_domain_expect_table_instance(
    tag_registry_with_user_table: InMemoryTagRegistry,
) -> None:
    """등록된 도메인에 대해 from_domain이 올바른 테이블 인스턴스를 반환함을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry_with_user_table)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    result = registry.from_domain(user)

    assert isinstance(result, UserTable)
    assert result.uid == user.uid
    assert result.username == user.username
    assert result.password == user.password


def test_from_domain_unregistered_domain_expect_error(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """등록되지 않은 도메인에 대해 from_domain이 NoSchemaFoundFromDomainError를 발생시킴을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry)
    user = User(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        username="testuser",
        password="testpass",
    )

    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.from_domain(user)


def test_get_type_registered_domain_expect_table_type(
    tag_registry_with_user_table: InMemoryTagRegistry,
) -> None:
    """등록된 도메인에 대해 get_type이 올바른 테이블 타입을 반환함을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry_with_user_table)

    result = registry.get_type(User)

    assert result is UserTable


def test_get_type_unregistered_domain_expect_error(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """등록되지 않은 도메인에 대해 get_type이 NoSchemaFoundFromDomainError를 발생시킴을 검증한다."""
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry)

    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.get_type(User)


def test_register_non_mappable_table_expect_metadata_only(
    tag_registry: InMemoryTagRegistry,
) -> None:
    """Non-mappable 테이블은 metadata에만 등록되고 도메인 매핑에는 등록되지 않음을 검증한다."""

    @Table()
    class InfrastructureTable(AbstractTable):
        __tablename__ = "test_infrastructure"

        id: Mapped[int] = mapped_column(Integer(), primary_key=True)
        data: Mapped[str] = mapped_column(String(), nullable=False)

    tag_registry.register_tag(Table.get(InfrastructureTable))
    registry = SchemaRegistry()
    registry.set_tag_registry(tag_registry)

    # Table should be in metadata
    assert "test_infrastructure" in registry.metadata.tables
    # But no domain-to-table mapping should exist
    with pytest.raises(NoSchemaFoundFromDomainError):
        registry.get_type(User)
