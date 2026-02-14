"""Integration tests for ModelRegistry functionality."""

import pytest
from sqlalchemy import UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from tests.apps.entities import Comment, Post, User, create_user

# =============================================================================
# Model Registration Tests
# =============================================================================


def test_registry_register_entities_expect_all_registered(
    registry: ModelRegistry,
) -> None:
    """TableRegistrationPostProcessor가 @Table 어노테이션 클래스를 자동 등록하는지 검증한다."""
    assert registry.is_registered(User)
    assert registry.is_registered(Post)
    assert registry.is_registered(Comment)


def test_registry_register_entities_expect_correct_table_names(
    registry: ModelRegistry,
) -> None:
    """등록된 엔티티의 테이블 이름이 @Table 어노테이션과 일치하는지 검증한다."""
    users_table = registry.registered_entities[User]
    posts_table = registry.registered_entities[Post]
    comments_table = registry.registered_entities[Comment]

    assert users_table.name == "users"
    assert posts_table.name == "posts"
    assert comments_table.name == "comments"


def test_registry_register_entities_expect_all_columns_created(
    registry: ModelRegistry,
) -> None:
    """등록된 엔티티의 모든 컬럼이 생성되는지 검증한다."""
    users_table = registry.registered_entities[User]
    column_names = {col.name for col in users_table.columns}
    expected_columns = {"id", "email", "username", "status", "created_at"}

    assert column_names == expected_columns


def test_registry_register_entities_expect_primary_key_set(
    registry: ModelRegistry,
) -> None:
    """Primary Key 제약조건이 올바르게 설정되는지 검증한다."""
    users_table = registry.registered_entities[User]
    pk_columns = [col.name for col in users_table.primary_key.columns]

    assert pk_columns == ["id"]


def test_registry_register_entities_expect_foreign_keys_created(
    registry: ModelRegistry,
) -> None:
    """Foreign Key 제약조건이 올바르게 생성되는지 검증한다."""
    posts_table = registry.registered_entities[Post]
    comments_table = registry.registered_entities[Comment]

    # Posts should have 1 FK (author_id -> users.id)
    assert len(posts_table.foreign_keys) == 1

    # Comments should have 2 FKs (post_id -> posts.id, author_id -> users.id)
    assert len(comments_table.foreign_keys) == 2


# =============================================================================
# Table-Level Constraint Tests
# =============================================================================


def test_registry_named_unique_constraint_expect_table_level(
    registry: ModelRegistry,
) -> None:
    """Named Unique 제약조건이 테이블 레벨에서 생성되는지 검증한다."""
    users_table = registry.registered_entities[User]

    # Find named unique constraint
    unique_constraints: list[UniqueConstraint] = [
        c
        for c in users_table.constraints
        if isinstance(c, UniqueConstraint) and c.name == "uq_users_email"
    ]

    assert len(unique_constraints) == 1
    constraint = unique_constraints[0]
    assert len(constraint.columns) == 1
    assert "email" in [col.name for col in constraint.columns]


def test_registry_named_index_expect_table_level(
    registry: ModelRegistry,
) -> None:
    """Named Index가 테이블 레벨에서 생성되는지 검증한다."""
    posts_table = registry.registered_entities[Post]

    # Find named index
    indexes = [idx for idx in posts_table.indexes if idx.name == "idx_posts_author_id"]

    assert len(indexes) == 1
    index = indexes[0]
    assert len(index.columns) == 1
    assert "author_id" in [col.name for col in index.columns]


@pytest.mark.asyncio
async def test_named_unique_constraint_violation_expect_integrity_error(
    session: AsyncSession,
) -> None:
    """Named Unique 제약조건 위반 시 IntegrityError가 발생하는지 검증한다."""
    user1 = create_user(email="duplicate@example.com")
    session.add(user1)
    await session.commit()

    user2 = create_user(email="duplicate@example.com")  # 중복 이메일
    session.add(user2)

    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_named_index_improves_query_performance_expect_index_used(
    session: AsyncSession,
) -> None:
    """Named Index가 쿼리에 사용될 수 있는지 검증한다 (인덱스 존재 여부)."""
    # 인덱스가 존재하는지 확인 (PostgreSQL 시스템 카탈로그 조회)
    result = await session.execute(
        text(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'posts' AND indexname = 'idx_posts_author_id'
            """
        )
    )
    index_name = result.scalar_one_or_none()

    assert index_name == "idx_posts_author_id"
