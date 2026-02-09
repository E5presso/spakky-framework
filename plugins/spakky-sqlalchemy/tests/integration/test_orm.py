"""Integration tests for SQLAlchemy ORM functionality."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from tests.apps.entities import (
    Comment,
    Post,
    User,
    UserStatus,
    create_post,
    create_user,
)

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
# CRUD Operation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_add_user_expect_persisted(
    session: AsyncSession,
) -> None:
    """User 엔티티를 세션에 추가하면 DB에 저장되는지 검증한다."""
    user = create_user(
        email="john@example.com",
        username="john_doe",
    )
    session.add(user)
    await session.commit()

    saved_user = await session.get(User, user.id)

    assert saved_user is not None
    assert saved_user.email == "john@example.com"
    assert saved_user.username == "john_doe"
    assert saved_user.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_session_get_user_expect_found(
    session: AsyncSession,
) -> None:
    """session.get()으로 User 엔티티를 조회할 수 있는지 검증한다."""
    user = create_user(email="reader@example.com")
    session.add(user)
    await session.commit()

    await session.refresh(user)
    found_user = await session.get(User, user.id)

    assert found_user is not None
    assert found_user.id == user.id
    assert found_user.email == "reader@example.com"


@pytest.mark.asyncio
async def test_session_update_user_expect_changed(
    session: AsyncSession,
) -> None:
    """User 엔티티 수정 후 commit하면 변경사항이 저장되는지 검증한다."""
    user = create_user(
        email="update@example.com",
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.commit()

    user.status = UserStatus.SUSPENDED
    await session.commit()

    updated_user = await session.get(User, user.id)

    assert updated_user is not None
    assert updated_user.status == UserStatus.SUSPENDED


@pytest.mark.asyncio
async def test_session_delete_user_expect_removed(
    session: AsyncSession,
) -> None:
    """User 엔티티를 삭제하면 DB에서 제거되는지 검증한다."""
    user = create_user(email="delete@example.com")
    session.add(user)
    await session.commit()

    user_id = user.id

    await session.delete(user)
    await session.commit()

    deleted_user = await session.get(User, user_id)

    assert deleted_user is None


# =============================================================================
# Relationship Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_add_post_with_author_expect_fk_set(
    session: AsyncSession,
) -> None:
    """Post 엔티티 생성 시 author_id FK가 올바르게 설정되는지 검증한다."""
    user = create_user(email="author@example.com")
    session.add(user)
    await session.commit()

    post = create_post(
        author_id=user.id,
        title="My First Post",
        content="Hello World!",
    )
    session.add(post)
    await session.commit()

    saved_post = await session.get(Post, post.id)

    assert saved_post is not None
    assert saved_post.author_id == user.id
    assert saved_post.title == "My First Post"


@pytest.mark.asyncio
async def test_session_delete_user_expect_posts_cascade_deleted(
    session: AsyncSession,
) -> None:
    """User 삭제 시 ON DELETE CASCADE로 관련 Post가 삭제되는지 검증한다."""
    user = create_user(email="cascade@example.com")
    session.add(user)
    await session.commit()

    post = create_post(author_id=user.id, title="Will be deleted")
    session.add(post)
    await session.commit()

    post_id = post.id

    await session.delete(user)
    await session.commit()

    # Expire all cached objects to force DB reload
    session.expire_all()

    deleted_post = await session.get(Post, post_id)

    assert deleted_post is None


@pytest.mark.asyncio
async def test_session_add_multiple_posts_expect_all_saved(
    session: AsyncSession,
) -> None:
    """한 User에 여러 Post를 추가할 수 있는지 검증한다."""
    user = create_user(email="multi@example.com")
    session.add(user)
    await session.commit()

    posts = [create_post(author_id=user.id, title=f"Post {i}") for i in range(3)]
    session.add_all(posts)
    await session.commit()

    result = await session.execute(
        text("SELECT COUNT(*) FROM posts WHERE author_id = :author_id"),
        {"author_id": str(user.id)},
    )
    count = result.scalar_one()

    assert count == 3


# =============================================================================
# Enum Field Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_save_enum_field_expect_persisted_correctly(
    session: AsyncSession,
) -> None:
    """Enum 필드 값이 올바르게 저장되고 조회되는지 검증한다."""
    statuses = [UserStatus.ACTIVE, UserStatus.INACTIVE, UserStatus.SUSPENDED]
    users = []

    for i, status in enumerate(statuses):
        user = create_user(
            email=f"enum_{i}@example.com",
            status=status,
        )
        session.add(user)
        users.append(user)

    await session.commit()

    for user, expected_status in zip(users, statuses):
        found_user = await session.get(User, user.id)
        assert found_user is not None
        assert found_user.status == expected_status


# =============================================================================
# Query Operation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_execute_count_query_expect_correct_result(
    session: AsyncSession,
) -> None:
    """COUNT 쿼리가 올바른 결과를 반환하는지 검증한다."""
    users = [create_user(email=f"count_{i}@example.com") for i in range(7)]
    session.add_all(users)
    await session.commit()

    result = await session.execute(text("SELECT COUNT(*) FROM users"))
    count = result.scalar_one()

    assert count == 7
