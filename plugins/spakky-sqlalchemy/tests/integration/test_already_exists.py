"""EntityAlreadyExistsError integration tests against PostgreSQL."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.utils.uuid import uuid7
from spakky.data.persistency.repository import (
    EntityAlreadyExistsError,
    IAsyncGenericRepository,
    IGenericRepository,
)
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from tests.apps.models.user import User
from tests.apps.orm.user import UserTable

LOCK_WAIT_POLL_SECONDS = 0.02
LOCK_WAIT_POLL_LIMIT = 500


@pytest.fixture(name="async_users", scope="function")
def async_users_fixture(app: SpakkyApplication) -> IAsyncGenericRepository[User, UUID]:
    """Get async User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


@pytest.fixture(name="users", scope="function")
def users_fixture(app: SpakkyApplication) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


def _user(username: str, email: str) -> User:
    return User.create(username=username, email=email, password_hash="hashed")


@pytest.mark.asyncio
async def test_async_save_new_user_with_taken_username_expect_already_exists_then_readable(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """이미 있는 username으로 새 집합체를 저장하면 EntityAlreadyExistsError이고, 새 트랜잭션에서 기존 것을 읽을 수 있다."""
    existing = _user(f"taken_{unique_id}", f"first_{unique_id}@example.com")
    async with async_transaction:
        await async_users.save(existing)
    duplicate = _user(f"taken_{unique_id}", f"second_{unique_id}@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        async with async_transaction:
            await async_users.save(duplicate)

    assert error.value.args == (duplicate.uid,)
    async with async_transaction:
        assert (await async_users.get(existing.uid)).username == existing.username
        assert await async_users.get_or_none(duplicate.uid) is None


@pytest.mark.asyncio
async def test_async_save_new_user_racing_uncommitted_insert_expect_late_one_already_exists(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    async_connection_manager: AsyncConnectionManager,
    unique_id: str,
) -> None:
    """두 트랜잭션이 같은 유일 키의 새 행을 함께 만들면 늦은 쪽의 INSERT가 EntityAlreadyExistsError로 끝난다."""
    username = f"race_{unique_id}"
    engine = async_connection_manager.connection
    late = _user(username, f"late_{unique_id}@example.com")

    async def save_late() -> None:
        async with async_transaction:
            await async_users.save(late)

    async with engine.connect() as early, engine.connect() as observer:
        await early.execute(
            insert(UserTable).values(
                uid=uuid7(),
                version=uuid7(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                username=username,
                email=f"early_{unique_id}@example.com",
                password_hash="hashed",
            )
        )
        late_save = asyncio.create_task(save_late())
        for _ in range(LOCK_WAIT_POLL_LIMIT):
            waiting = (
                await observer.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND query LIKE :query"
                    ),
                    {"query": "INSERT INTO users%"},
                )
            ).scalar_one()
            await observer.rollback()
            if waiting > 0:
                break
            await asyncio.sleep(LOCK_WAIT_POLL_SECONDS)
        assert not late_save.done()
        await early.commit()

        with pytest.raises(EntityAlreadyExistsError):
            await late_save

    async with engine.connect() as connection:
        stored_emails = (
            (
                await connection.execute(
                    select(UserTable.email).where(UserTable.username == username)
                )
            )
            .scalars()
            .all()
        )
    assert stored_emails == [f"early_{unique_id}@example.com"]


@pytest.mark.asyncio
async def test_async_save_loaded_user_into_taken_username_expect_integrity_error(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """기존 행을 다른 집합체의 유일 키로 고치는 UPDATE의 유일 위반은 IntegrityError 그대로다."""
    first = _user(f"first_{unique_id}", f"first_{unique_id}@example.com")
    second = _user(f"second_{unique_id}", f"second_{unique_id}@example.com")
    async with async_transaction:
        await async_users.save_all([first, second])

    with pytest.raises(IntegrityError) as error:
        async with async_transaction:
            loaded = await async_users.get(second.uid)
            loaded.username = first.username
            await async_users.save(loaded)

    assert not isinstance(error.value, EntityAlreadyExistsError)


@pytest.mark.asyncio
async def test_async_save_all_new_users_with_taken_username_expect_already_exists(
    async_transaction: AsyncTransaction,
    async_users: IAsyncGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """save_all로 저장한 새 집합체가 유일 키와 부딪히면 새 집합체 식별자 목록을 담아 알린다."""
    existing = _user(f"taken_{unique_id}", f"first_{unique_id}@example.com")
    async with async_transaction:
        await async_users.save(existing)
    duplicate = _user(f"taken_{unique_id}", f"second_{unique_id}@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        async with async_transaction:
            await async_users.save_all([duplicate])

    assert error.value.args == ([duplicate.uid],)


def test_sync_save_new_user_with_taken_username_expect_already_exists(
    transaction: Transaction,
    users: IGenericRepository[User, UUID],
    unique_id: str,
) -> None:
    """동기 저장소도 이미 있는 username의 새 집합체 저장을 EntityAlreadyExistsError로 알린다."""
    existing = _user(f"taken_{unique_id}", f"first_{unique_id}@example.com")
    with transaction:
        users.save(existing)
    duplicate = _user(f"taken_{unique_id}", f"second_{unique_id}@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        with transaction:
            users.save(duplicate)

    assert error.value.args == (duplicate.uid,)
    with transaction:
        assert users.get(existing.uid).username == existing.username
