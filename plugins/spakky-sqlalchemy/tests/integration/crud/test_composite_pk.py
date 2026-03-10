"""Composite primary key CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.utils.uuid import uuid7
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IAsyncGenericRepository,
    IGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from tests.apps.models.user import User
from tests.apps.models.user_role import UserRole


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


@pytest.fixture(name="async_user_repository", scope="function")
def async_user_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[User, UUID]:
    """Get async User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


@pytest.fixture(name="user_role_repository", scope="function")
def user_role_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[UserRole, tuple[UUID, UUID]]:
    """Get sync UserRole repository from application container."""
    return app.container.get(type_=IGenericRepository[UserRole, tuple[UUID, UUID]])


@pytest.fixture(name="async_user_role_repository", scope="function")
def async_user_role_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[UserRole, tuple[UUID, UUID]]:
    """Get async UserRole repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[UserRole, tuple[UUID, UUID]])


def create_test_user(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> User:
    """Create a test user for FK constraint."""
    user = User.create(
        username=f"cpk_user_{uuid4().hex[:8]}",
        email=f"cpk_user_{uuid4().hex[:8]}@example.com",
        password_hash="hashed",
    )
    with transaction:
        return user_repository.save(user)


async def create_test_user_async(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> User:
    """Create a test user for FK constraint."""
    user = User.create(
        username=f"cpk_user_{uuid4().hex[:8]}",
        email=f"cpk_user_{uuid4().hex[:8]}@example.com",
        password_hash="hashed",
    )
    async with async_transaction:
        return await user_repository.save(user)


# === Sync Composite PK Tests ===


def test_sync_composite_pk_save_expect_persisted(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK 엔티티를 save하면 데이터베이스에 영속화된다."""
    user = create_test_user(transaction, user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    with transaction:
        saved = user_role_repository.save(user_role)

        assert saved.uid == (user.uid, role_id)
        assert saved.user_id == user.uid
        assert saved.role_id == role_id


def test_sync_composite_pk_get_expect_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK로 get하면 해당 엔티티가 반환된다."""
    user = create_test_user(transaction, user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    with transaction:
        user_role_repository.save(user_role)
        retrieved = user_role_repository.get((user.uid, role_id))

        assert retrieved.uid == (user.uid, role_id)


def test_sync_composite_pk_get_nonexistent_expect_error(
    transaction: Transaction,
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """존재하지 않는 복합 PK로 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_pk = (uuid7(), uuid7())

    with transaction:
        with pytest.raises(EntityNotFoundError):
            user_role_repository.get(nonexistent_pk)


def test_sync_composite_pk_contains_expect_true(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """존재하는 복합 PK로 contains하면 True가 반환된다."""
    user = create_test_user(transaction, user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    with transaction:
        user_role_repository.save(user_role)
        exists = user_role_repository.contains((user.uid, role_id))

        assert exists is True


def test_sync_composite_pk_range_expect_all_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """여러 복합 PK로 range하면 해당 엔티티들이 반환된다."""
    user = create_test_user(transaction, user_repository)
    role_ids = [uuid7() for _ in range(3)]
    user_roles = [UserRole.create(user_id=user.uid, role_id=rid) for rid in role_ids]
    pks = [(user.uid, rid) for rid in role_ids]

    with transaction:
        user_role_repository.save_all(user_roles)
        retrieved = user_role_repository.range(pks)

        assert len(retrieved) == 3
        retrieved_pks = {ur.uid for ur in retrieved}
        assert retrieved_pks == set(pks)


def test_sync_composite_pk_delete_expect_removed(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
    user_role_repository: IGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK 엔티티를 delete하면 데이터베이스에서 제거된다."""
    user = create_test_user(transaction, user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    with transaction:
        user_role_repository.save(user_role)
        user_role_repository.delete(user_role)
        exists = user_role_repository.contains((user.uid, role_id))

        assert exists is False


# === Async Composite PK Tests ===


@pytest.mark.asyncio
async def test_async_composite_pk_save_expect_persisted(
    async_transaction: AsyncTransaction,
    async_user_repository: IAsyncGenericRepository[User, UUID],
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK 엔티티를 async save하면 데이터베이스에 영속화된다."""
    user = await create_test_user_async(async_transaction, async_user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    async with async_transaction:
        saved = await async_user_role_repository.save(user_role)

        assert saved.uid == (user.uid, role_id)
        assert saved.user_id == user.uid
        assert saved.role_id == role_id


@pytest.mark.asyncio
async def test_async_composite_pk_get_expect_returned(
    async_transaction: AsyncTransaction,
    async_user_repository: IAsyncGenericRepository[User, UUID],
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK로 async get하면 해당 엔티티가 반환된다."""
    user = await create_test_user_async(async_transaction, async_user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    async with async_transaction:
        await async_user_role_repository.save(user_role)
        retrieved = await async_user_role_repository.get((user.uid, role_id))

        assert retrieved.uid == (user.uid, role_id)


@pytest.mark.asyncio
async def test_async_composite_pk_get_nonexistent_expect_error(
    async_transaction: AsyncTransaction,
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """존재하지 않는 복합 PK로 async get하면 EntityNotFoundError가 발생한다."""
    nonexistent_pk = (uuid7(), uuid7())

    async with async_transaction:
        with pytest.raises(EntityNotFoundError):
            await async_user_role_repository.get(nonexistent_pk)


@pytest.mark.asyncio
async def test_async_composite_pk_contains_expect_true(
    async_transaction: AsyncTransaction,
    async_user_repository: IAsyncGenericRepository[User, UUID],
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """존재하는 복합 PK로 async contains하면 True가 반환된다."""
    user = await create_test_user_async(async_transaction, async_user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    async with async_transaction:
        await async_user_role_repository.save(user_role)
        exists = await async_user_role_repository.contains((user.uid, role_id))

        assert exists is True


@pytest.mark.asyncio
async def test_async_composite_pk_range_expect_all_returned(
    async_transaction: AsyncTransaction,
    async_user_repository: IAsyncGenericRepository[User, UUID],
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """여러 복합 PK로 async range하면 해당 엔티티들이 반환된다."""
    user = await create_test_user_async(async_transaction, async_user_repository)
    role_ids = [uuid7() for _ in range(3)]
    user_roles = [UserRole.create(user_id=user.uid, role_id=rid) for rid in role_ids]
    pks = [(user.uid, rid) for rid in role_ids]

    async with async_transaction:
        await async_user_role_repository.save_all(user_roles)
        retrieved = await async_user_role_repository.range(pks)

        assert len(retrieved) == 3
        retrieved_pks = {ur.uid for ur in retrieved}
        assert retrieved_pks == set(pks)


@pytest.mark.asyncio
async def test_async_composite_pk_delete_expect_removed(
    async_transaction: AsyncTransaction,
    async_user_repository: IAsyncGenericRepository[User, UUID],
    async_user_role_repository: IAsyncGenericRepository[UserRole, tuple[UUID, UUID]],
) -> None:
    """복합 PK 엔티티를 async delete하면 데이터베이스에서 제거된다."""
    user = await create_test_user_async(async_transaction, async_user_repository)
    role_id = uuid7()
    user_role = UserRole.create(user_id=user.uid, role_id=role_id)

    async with async_transaction:
        await async_user_role_repository.save(user_role)
        await async_user_role_repository.delete(user_role)
        exists = await async_user_role_repository.contains((user.uid, role_id))

        assert exists is False
