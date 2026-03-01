"""User entity CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IAsyncGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models.user import User


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[User, UUID]:
    """Get User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


@pytest.mark.asyncio
async def test_user_save_expect_persisted(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """새 User를 save하면 데이터베이스에 영속화된다."""
    user = User.create(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )

    async with async_transaction:
        saved_user = await user_repository.save(user)

        assert saved_user.uid == user.uid
        assert saved_user.username == "testuser"
        assert saved_user.email == "test@example.com"


@pytest.mark.asyncio
async def test_user_save_all_expect_all_persisted(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 User를 save_all하면 모두 영속화된다."""
    users = [
        User.create(
            username=f"user_{i}",
            email=f"user_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        saved_users = await user_repository.save_all(users)

        assert len(saved_users) == 3
        for i, saved_user in enumerate(saved_users):
            assert saved_user.uid == users[i].uid


@pytest.mark.asyncio
async def test_user_get_existing_expect_returned(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 get하면 해당 엔티티가 반환된다."""
    user = User.create(
        username="findme",
        email="findme@example.com",
        password_hash="hashed",
    )

    async with async_transaction:
        await user_repository.save(user)
        retrieved_user = await user_repository.get(user.uid)

        assert retrieved_user.uid == user.uid
        assert retrieved_user.username == "findme"
        assert retrieved_user.email == "findme@example.com"


@pytest.mark.asyncio
async def test_user_get_nonexistent_expect_entity_not_found_error(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            await user_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


@pytest.mark.asyncio
async def test_user_get_or_none_existing_expect_returned(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 get_or_none하면 해당 엔티티가 반환된다."""
    user = User.create(
        username="nullable_find",
        email="nullable@example.com",
        password_hash="hashed",
    )

    async with async_transaction:
        await user_repository.save(user)
        retrieved_user = await user_repository.get_or_none(user.uid)

        assert retrieved_user is not None
        assert retrieved_user.uid == user.uid


@pytest.mark.asyncio
async def test_user_get_or_none_nonexistent_expect_none(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        retrieved_user = await user_repository.get_or_none(nonexistent_id)

        assert retrieved_user is None


@pytest.mark.asyncio
async def test_user_contains_existing_expect_true(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 User ID로 contains하면 True가 반환된다."""
    user = User.create(
        username="exists_check",
        email="exists@example.com",
        password_hash="hashed",
    )

    async with async_transaction:
        await user_repository.save(user)
        exists = await user_repository.contains(user.uid)

        assert exists is True


@pytest.mark.asyncio
async def test_user_contains_nonexistent_expect_false(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        exists = await user_repository.contains(nonexistent_id)

        assert exists is False


@pytest.mark.asyncio
async def test_user_range_existing_expect_all_returned(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 User ID로 range하면 해당 엔티티들이 반환된다."""
    users = [
        User.create(
            username=f"range_user_{i}",
            email=f"range_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]
    user_ids = [user.uid for user in users]

    async with async_transaction:
        await user_repository.save_all(users)
        retrieved_users = await user_repository.range(user_ids)

        assert len(retrieved_users) == 3
        retrieved_ids = {user.uid for user in retrieved_users}
        assert retrieved_ids == set(user_ids)


@pytest.mark.asyncio
async def test_user_range_partial_existing_expect_only_existing_returned(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    user = User.create(
        username="partial_range",
        email="partial@example.com",
        password_hash="hashed",
    )
    nonexistent_id = uuid4()

    async with async_transaction:
        await user_repository.save(user)
        retrieved_users = await user_repository.range([user.uid, nonexistent_id])

        assert len(retrieved_users) == 1
        assert retrieved_users[0].uid == user.uid


@pytest.mark.asyncio
async def test_user_range_empty_list_expect_empty_result(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    async with async_transaction:
        retrieved_users = await user_repository.range([])

        assert len(retrieved_users) == 0


@pytest.mark.asyncio
async def test_user_delete_existing_expect_removed(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 delete하면 데이터베이스에서 제거된다."""
    user = User.create(
        username="to_delete",
        email="delete@example.com",
        password_hash="hashed",
    )

    async with async_transaction:
        await user_repository.save(user)
        deleted_user = await user_repository.delete(user)

        assert deleted_user.uid == user.uid
        assert await user_repository.contains(user.uid) is False


@pytest.mark.asyncio
async def test_user_delete_all_expect_all_removed(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 User를 delete_all하면 모두 제거된다."""
    users = [
        User.create(
            username=f"delete_all_{i}",
            email=f"delete_all_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        await user_repository.save_all(users)
        deleted_users = await user_repository.delete_all(users)

        assert len(deleted_users) == 3
        for user in users:
            assert await user_repository.contains(user.uid) is False


@pytest.mark.asyncio
async def test_user_save_updated_expect_changes_persisted(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """기존 User를 수정 후 save하면 변경사항이 영속화된다."""
    user = User.create(
        username="original",
        email="original@example.com",
        password_hash="original_hash",
    )

    async with async_transaction:
        await user_repository.save(user)
        user.username = "updated"
        user.email = "updated@example.com"
        await user_repository.save(user)
        retrieved_user = await user_repository.get(user.uid)

        assert retrieved_user.username == "updated"
        assert retrieved_user.email == "updated@example.com"
