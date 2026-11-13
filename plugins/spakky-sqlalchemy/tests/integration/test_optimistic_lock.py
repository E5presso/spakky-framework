"""Optimistic locking integration tests against PostgreSQL."""

from uuid import UUID

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    IAsyncGenericRepository,
    IGenericRepository,
    VersionConflictError,
)

from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from tests.apps.models.user import User


@pytest.fixture(name="async_users", scope="function")
def async_users_fixture(app: SpakkyApplication) -> IAsyncGenericRepository[User, UUID]:
    """Get async User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


@pytest.fixture(name="users", scope="function")
def users_fixture(app: SpakkyApplication) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


def _new_user(unique_id: str) -> User:
    return User.create(
        username=f"lock_{unique_id}",
        email=f"lock_{unique_id}@example.com",
        password_hash="hashed",
    )


@pytest.mark.asyncio
async def test_async_save_new_user_expect_inserted_with_current_version(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """새 애그리거트를 저장하면 현재 version으로 INSERT된다."""
    user = _new_user(unique_id)

    async with async_transaction:
        await async_users.save(user)
    async with async_transaction:
        stored = await async_users.get(user.uid)

    assert stored.version == user.version
    assert user.persisted_version == user.version


@pytest.mark.asyncio
async def test_async_save_loaded_user_after_change_expect_updated(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """다른 writer가 없으면 불러온 애그리거트의 변경이 저장되고 version이 바뀐다."""
    user = _new_user(unique_id)
    async with async_transaction:
        await async_users.save(user)

    async with async_transaction:
        loaded = await async_users.get(user.uid)
        loaded.password_hash = "changed"
        await async_users.save(loaded)
    async with async_transaction:
        stored = await async_users.get(user.uid)

    assert stored.password_hash == "changed"
    assert stored.version == loaded.version
    assert stored.version != user.version


@pytest.mark.asyncio
async def test_async_save_from_two_units_of_work_expect_second_version_conflict(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """두 작업 단위가 같은 행을 읽고 모두 저장하면 두 번째 저장이 VersionConflictError로 실패한다."""
    user = _new_user(unique_id)
    async with async_transaction:
        await async_users.save(user)
    async with async_transaction:
        first = await async_users.get(user.uid)
    async with async_transaction:
        second = await async_users.get(user.uid)

    first.password_hash = "first"
    async with async_transaction:
        await async_users.save(first)
    second.password_hash = "second"
    with pytest.raises(VersionConflictError):
        async with async_transaction:
            await async_users.save(second)

    async with async_transaction:
        stored = await async_users.get(user.uid)
    assert stored.password_hash == "first"
    assert stored.version == first.version


@pytest.mark.asyncio
async def test_async_save_same_instance_twice_expect_both_updates_stored(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """한 인스턴스를 한 트랜잭션에서 두 번 연속 저장해도 모두 성공한다."""
    user = _new_user(unique_id)
    async with async_transaction:
        await async_users.save(user)

    async with async_transaction:
        loaded = await async_users.get(user.uid)
        loaded.password_hash = "once"
        await async_users.save(loaded)
        loaded.password_hash = "twice"
        await async_users.save(loaded)
    async with async_transaction:
        stored = await async_users.get(user.uid)

    assert stored.password_hash == "twice"
    assert stored.version == loaded.version


@pytest.mark.asyncio
async def test_async_delete_user_with_old_version_expect_version_conflict(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """다른 작업 단위가 먼저 변경한 행을 오래된 인스턴스로 삭제하면 VersionConflictError가 발생한다."""
    user = _new_user(unique_id)
    async with async_transaction:
        await async_users.save(user)
    async with async_transaction:
        stale = await async_users.get(user.uid)
    async with async_transaction:
        winner = await async_users.get(user.uid)
        winner.password_hash = "winner"
        await async_users.save(winner)

    with pytest.raises(VersionConflictError):
        async with async_transaction:
            await async_users.delete(stale)

    async with async_transaction:
        assert await async_users.contains(user.uid)


def test_sync_save_user_with_old_version_expect_version_conflict(
    transaction: Transaction,
    users: IGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """오래된 version을 들고 있는 인스턴스를 저장하면 VersionConflictError가 발생한다."""
    user = _new_user(f"sync_{unique_id}")
    with transaction:
        users.save(user)
    with transaction:
        stale = users.get(user.uid)
    with transaction:
        winner = users.get(user.uid)
        winner.password_hash = "winner"
        users.save(winner)

    stale.password_hash = "stale"
    with pytest.raises(VersionConflictError):
        with transaction:
            users.save(stale)

    with transaction:
        assert users.get(user.uid).password_hash == "winner"


def test_sync_save_same_instance_across_transactions_expect_updated(
    transaction: Transaction,
    users: IGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """저장에 성공한 인스턴스는 다음 트랜잭션에서 다시 변경·저장할 수 있다."""
    user = _new_user(f"sync_{unique_id}")
    with transaction:
        users.save(user)

    user.password_hash = "second"
    with transaction:
        users.save(user)
    user.password_hash = "third"
    with transaction:
        users.save(user)

    with transaction:
        stored = users.get(user.uid)
    assert stored.password_hash == "third"
    assert stored.version == user.version
