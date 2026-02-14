"""Integration tests for SQLAlchemy session CRUD operations."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.apps.entities import User, UserStatus, create_user

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
