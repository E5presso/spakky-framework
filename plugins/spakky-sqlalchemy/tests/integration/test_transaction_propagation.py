"""실제 PostgreSQL에서 중첩된 transaction scope(propagation)의 commit·rollback을 검증한다."""

from uuid import UUID

import pytest
from spakky.data.persistency.error import TransactionRollbackOnlyError
from spakky.data.persistency.transaction import Propagation
from sqlalchemy import select

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from tests.apps.models import User
from tests.apps.orm import UserTable


class InnerFailureError(Exception):
    """안쪽 scope에서 올라가는 업무 예외."""


class OuterFailureError(Exception):
    """바깥 scope에서 올라가는 업무 예외."""


def new_user(name: str) -> User:
    """겹치지 않는 사용자 aggregate를 만든다."""
    return User.create(
        username=name,
        email=f"{name}@example.com",
        password_hash="propagation_hash",
    )


async def stored(transaction: AsyncTransaction, uid: UUID) -> bool:
    """새 transaction에서 그 사용자가 commit되어 있는지 본다."""
    async with transaction:
        row = (
            await transaction.session.execute(
                select(UserTable).where(UserTable.uid == uid)
            )
        ).scalar_one_or_none()
        return row is not None


def stored_sync(transaction: Transaction, uid: UUID) -> bool:
    """새 동기 transaction에서 그 사용자가 commit되어 있는지 본다."""
    with transaction:
        row = transaction.session.execute(
            select(UserTable).where(UserTable.uid == uid)
        ).scalar_one_or_none()
        return row is not None


@pytest.mark.asyncio
async def test_async_required_inside_required_expect_same_session_single_commit(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """합쳐진 안쪽은 같은 session을 쓰고, 바깥이 끝난 뒤 둘 다 commit된다."""
    outer_user = new_user(f"req_outer_{unique_id}")
    inner_user = new_user(f"req_inner_{unique_id}")

    async with async_transaction.scope():
        outer_session = async_transaction.session
        async_transaction.session.add(schema_registry.from_domain(outer_user))
        async with async_transaction.scope(Propagation.REQUIRED):
            assert async_transaction.session is outer_session
            async_transaction.session.add(schema_registry.from_domain(inner_user))
        assert async_transaction.session is outer_session

    assert await stored(async_transaction, outer_user.uid)
    assert await stored(async_transaction, inner_user.uid)


@pytest.mark.asyncio
async def test_async_joined_failure_swallowed_expect_nothing_committed(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """안쪽 실패를 바깥이 삼켜도 전체가 rollback되고 TransactionRollbackOnlyError가 난다."""
    outer_user = new_user(f"ro_outer_{unique_id}")
    inner_user = new_user(f"ro_inner_{unique_id}")

    with pytest.raises(TransactionRollbackOnlyError):
        async with async_transaction.scope():
            async_transaction.session.add(schema_registry.from_domain(outer_user))
            try:
                async with async_transaction.scope():
                    async_transaction.session.add(
                        schema_registry.from_domain(inner_user)
                    )
                    raise InnerFailureError()
            except InnerFailureError:
                pass

    assert not await stored(async_transaction, outer_user.uid)
    assert not await stored(async_transaction, inner_user.uid)


@pytest.mark.asyncio
async def test_async_requires_new_expect_inner_survives_outer_rollback(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """REQUIRES_NEW 안쪽은 새 session으로 따로 commit되어 바깥 rollback 뒤에도 남는다."""
    outer_user = new_user(f"new_outer_{unique_id}")
    inner_user = new_user(f"new_inner_{unique_id}")

    with pytest.raises(OuterFailureError):
        async with async_transaction.scope():
            outer_session = async_transaction.session
            async_transaction.session.add(schema_registry.from_domain(outer_user))
            await async_transaction.session.flush()
            async with async_transaction.scope(Propagation.REQUIRES_NEW):
                assert async_transaction.session is not outer_session
                unseen = (
                    await async_transaction.session.execute(
                        select(UserTable).where(UserTable.uid == outer_user.uid)
                    )
                ).scalar_one_or_none()
                assert unseen is None
                async_transaction.session.add(schema_registry.from_domain(inner_user))
            assert async_transaction.session is outer_session
            raise OuterFailureError()

    assert not await stored(async_transaction, outer_user.uid)
    assert await stored(async_transaction, inner_user.uid)


@pytest.mark.asyncio
async def test_async_requires_new_failure_expect_outer_still_commits(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """REQUIRES_NEW 안쪽만 rollback되고 바깥은 commit된다."""
    outer_user = new_user(f"newfail_outer_{unique_id}")
    inner_user = new_user(f"newfail_inner_{unique_id}")

    async with async_transaction.scope():
        async_transaction.session.add(schema_registry.from_domain(outer_user))
        try:
            async with async_transaction.scope(Propagation.REQUIRES_NEW):
                async_transaction.session.add(schema_registry.from_domain(inner_user))
                raise InnerFailureError()
        except InnerFailureError:
            pass

    assert await stored(async_transaction, outer_user.uid)
    assert not await stored(async_transaction, inner_user.uid)


def test_sync_requires_new_expect_inner_survives_outer_rollback(
    schema_registry: SchemaRegistry,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """동기 REQUIRES_NEW도 따로 commit되어 바깥 rollback 뒤에 남는다."""
    outer_user = new_user(f"sync_new_outer_{unique_id}")
    inner_user = new_user(f"sync_new_inner_{unique_id}")

    with pytest.raises(OuterFailureError):
        with transaction.scope():
            outer_session = transaction.session
            transaction.session.add(schema_registry.from_domain(outer_user))
            with transaction.scope(Propagation.REQUIRES_NEW):
                assert transaction.session is not outer_session
                transaction.session.add(schema_registry.from_domain(inner_user))
            assert transaction.session is outer_session
            raise OuterFailureError()

    assert not stored_sync(transaction, outer_user.uid)
    assert stored_sync(transaction, inner_user.uid)


def test_sync_joined_failure_swallowed_expect_nothing_committed(
    schema_registry: SchemaRegistry,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """동기에서도 삼킨 안쪽 실패는 전체 rollback과 TransactionRollbackOnlyError로 끝난다."""
    outer_user = new_user(f"sync_ro_outer_{unique_id}")

    with pytest.raises(TransactionRollbackOnlyError):
        with transaction.scope():
            transaction.session.add(schema_registry.from_domain(outer_user))
            try:
                with transaction.scope():
                    raise InnerFailureError()
            except InnerFailureError:
                pass

    assert not stored_sync(transaction, outer_user.uid)
