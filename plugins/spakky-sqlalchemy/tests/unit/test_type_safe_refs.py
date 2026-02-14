"""Unit tests for EntityRef lambda accessor support."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.entity_ref import EntityRef
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.table import Table

# =============================================================================
# Test entities for type-safe references
# =============================================================================


@dataclass
class DummyUser:
    """Test entity representing a user (no @Table annotation)."""

    id: UUID
    name: str
    email: str
    posts: list["DummyPost"]


@dataclass
class DummyPost:
    """Test entity representing a post with FK to user (no @Table annotation)."""

    id: UUID
    author_id: UUID
    title: str
    author: DummyUser


@Table(table_name="custom_users")
@dataclass
class TableAnnotatedUser:
    """Test entity with @Table annotation."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    name: str


# =============================================================================
# EntityRef with type-based entity (lambda accessor required)
# =============================================================================


def test_entity_ref_name_with_lambda_expect_field_name_extracted() -> None:
    """EntityRef를 lambda accessor로 생성하면 필드 이름이 추출되어야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    result = ref.name

    assert result == "id"


def test_entity_ref_name_with_lambda_complex_field_expect_correct_name() -> None:
    """복잡한 필드명에 대한 lambda accessor도 올바르게 추출되어야 한다."""
    ref = EntityRef(DummyPost, lambda t: t.author_id)

    result = ref.name

    assert result == "author_id"


def test_entity_ref_column_name_with_lambda_expect_correct_value() -> None:
    """EntityRef를 lambda accessor로 생성하면 올바른 column_name이 반환되어야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    assert ref.column_name == "id"


def test_entity_ref_entity_name_with_class_expect_class_name() -> None:
    """EntityRef.entity_name은 엔티티 클래스명을 반환해야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    assert ref.entity_name == "DummyUser"


def test_entity_ref_to_fk_string_expect_table_dot_column() -> None:
    """EntityRef.to_fk_string()은 'table.column' 형식을 반환해야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    result = ref.to_fk_string()

    assert result == "dummy_user.id"


def test_entity_ref_repr_with_lambda_expect_readable_format() -> None:
    """EntityRef.__repr__()은 읽기 쉬운 형식을 반환해야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    result = repr(ref)

    assert "EntityRef" in result
    assert "DummyUser" in result
    assert "id" in result


def test_entity_ref_field_name_with_lambda_expect_correct_value() -> None:
    """EntityRef를 lambda accessor로 생성하면 올바른 field_name이 반환되어야 한다."""
    ref = EntityRef(DummyPost, lambda t: t.author_id)

    assert ref.field_name == "author_id"


def test_entity_ref_entity_attribute_with_class_expect_class() -> None:
    """클래스 참조로 EntityRef를 생성하면 entity 속성이 클래스여야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.posts)

    assert ref.entity is DummyUser


# =============================================================================
# EntityRef with string-based entity (forward reference, string field required)
# =============================================================================


def test_entity_ref_name_with_string_entity_expect_string_returned() -> None:
    """문자열 엔티티로 EntityRef를 생성하면 name이 그대로 반환되어야 한다."""
    ref = EntityRef("User", "my_field")

    result = ref.name

    assert result == "my_field"


def test_entity_ref_to_fk_string_with_string_entity_expect_correct_format() -> None:
    """문자열 엔티티 이름으로 EntityRef를 생성하면 to_fk_string이 올바른 형식을 반환해야 한다."""
    ref = EntityRef("User", "id")

    result = ref.to_fk_string()

    assert result == "user.id"


def test_entity_ref_entity_name_with_string_expect_string() -> None:
    """문자열로 EntityRef를 생성하면 entity_name이 문자열 그대로여야 한다."""
    ref = EntityRef("User", "posts")

    assert ref.entity_name == "User"


def test_entity_ref_entity_attribute_with_string_expect_string() -> None:
    """문자열로 EntityRef를 생성하면 entity 속성이 문자열이어야 한다."""
    ref = EntityRef("User", "posts")

    assert ref.entity == "User"


def test_entity_ref_table_name_without_table_annotation_expect_snake_case() -> None:
    """@Table 어노테이션이 없는 클래스는 클래스명을 snake_case로 변환해야 한다."""
    ref = EntityRef(DummyUser, lambda t: t.id)

    # DummyUser는 @Table이 없으므로 클래스명을 snake_case로 변환
    result = ref.table_name

    assert result == "dummy_user"
