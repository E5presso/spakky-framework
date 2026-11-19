"""실제 PostgreSQL에서 중첩된 transaction scope(propagation)의 commit·rollback을 검증한다."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from uuid import UUID

import pytest
from spakky.data.persistency.error import (
    TransactionAlreadyFinishedError,
    TransactionRollbackOnlyError,
)
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


@pytest.mark.asyncio
async def test_async_concurrent_requires_new_expect_each_task_commits_own_session(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """한 요청의 두 task가 동시에 연 REQUIRES_NEW는 각자의 session으로만 commit·rollback한다."""
    outer_user = new_user(f"conc_outer_{unique_id}")
    a_user = new_user(f"conc_a_{unique_id}")
    b_user = new_user(f"conc_b_{unique_id}")
    a_opened = asyncio.Event()
    b_opened = asyncio.Event()
    a_finished = asyncio.Event()

    async def a() -> None:
        async with async_transaction.scope(Propagation.REQUIRES_NEW):
            mine = async_transaction.session
            mine.add(schema_registry.from_domain(a_user))
            await mine.flush()
            a_opened.set()
            await b_opened.wait()
            assert async_transaction.session is mine
        a_finished.set()

    async def b() -> None:
        await a_opened.wait()
        async with async_transaction.scope(Propagation.REQUIRES_NEW):
            mine = async_transaction.session
            mine.add(schema_registry.from_domain(b_user))
            await mine.flush()
            b_opened.set()
            await a_finished.wait()
            assert async_transaction.session is mine
            raise InnerFailureError()

    async with async_transaction.scope():
        outer_session = async_transaction.session
        outer_session.add(schema_registry.from_domain(outer_user))
        results = await asyncio.gather(a(), b(), return_exceptions=True)
        assert results[0] is None
        assert isinstance(results[1], InnerFailureError)
        assert async_transaction.session is outer_session

    assert await stored(async_transaction, outer_user.uid)
    assert await stored(async_transaction, a_user.uid)
    assert not await stored(async_transaction, b_user.uid)


@pytest.mark.asyncio
async def test_async_joined_failure_in_child_task_expect_nothing_committed(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """gather로 부른 자식 task의 합쳐진 실패를 삼켜도 바깥은 commit하지 않는다."""
    outer_user = new_user(f"child_ro_outer_{unique_id}")

    async def child() -> None:
        async with async_transaction.scope(Propagation.REQUIRED):
            raise InnerFailureError()

    with pytest.raises(TransactionRollbackOnlyError):
        async with async_transaction.scope():
            async_transaction.session.add(schema_registry.from_domain(outer_user))
            await asyncio.gather(child(), return_exceptions=True)

    assert not await stored(async_transaction, outer_user.uid)


def test_sync_concurrent_requires_new_threads_expect_each_thread_commits_own(
    schema_registry: SchemaRegistry,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """context를 복사한 두 thread의 REQUIRES_NEW는 각자의 session으로만 commit·rollback한다."""
    outer_user = new_user(f"sync_conc_outer_{unique_id}")
    users = {
        "a": new_user(f"sync_conc_a_{unique_id}"),
        "b": new_user(f"sync_conc_b_{unique_id}"),
    }
    barrier = threading.Barrier(2)

    def child(name: str) -> None:
        with transaction.scope(Propagation.REQUIRES_NEW):
            mine = transaction.session
            mine.add(schema_registry.from_domain(users[name]))
            mine.flush()
            barrier.wait()
            assert transaction.session is mine
            barrier.wait()
            if name == "b":
                raise InnerFailureError()

    with transaction.scope():
        outer_session = transaction.session
        outer_session.add(schema_registry.from_domain(outer_user))
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                name: executor.submit(copy_context().run, child, name) for name in users
            }
            assert futures["a"].result() is None
            with pytest.raises(InnerFailureError):
                futures["b"].result()
        assert transaction.session is outer_session

    assert stored_sync(transaction, outer_user.uid)
    assert stored_sync(transaction, users["a"].uid)
    assert not stored_sync(transaction, users["b"].uid)


@pytest.mark.asyncio
async def test_async_child_task_after_outer_finished_expect_child_write_committed(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """바깥이 끝난 뒤 도는 fire-and-forget 자식 task의 REQUIRED는 새 session으로 자기 쓰기를 commit한다."""
    outer_user = new_user(f"ff_outer_{unique_id}")
    child_user = new_user(f"ff_child_{unique_id}")
    outer_finished = asyncio.Event()

    async def child() -> None:
        await outer_finished.wait()
        async with async_transaction.scope(Propagation.REQUIRED):
            async_transaction.session.add(schema_registry.from_domain(child_user))

    async with async_transaction.scope():
        async_transaction.session.add(schema_registry.from_domain(outer_user))
        task = asyncio.create_task(child())
    outer_finished.set()
    await task

    assert await stored(async_transaction, outer_user.uid)
    assert await stored(async_transaction, child_user.uid)


def test_sync_thread_after_outer_finished_expect_thread_write_committed(
    schema_registry: SchemaRegistry,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """바깥이 끝난 뒤 도는 thread의 REQUIRED는 새 session으로 자기 쓰기를 commit한다."""
    outer_user = new_user(f"ff_sync_outer_{unique_id}")
    child_user = new_user(f"ff_sync_child_{unique_id}")
    outer_finished = threading.Event()

    def child() -> None:
        outer_finished.wait()
        with transaction.scope(Propagation.REQUIRED):
            transaction.session.add(schema_registry.from_domain(child_user))

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            transaction.session.add(schema_registry.from_domain(outer_user))
            future = executor.submit(copy_context().run, child)
        outer_finished.set()
        future.result()

    assert stored_sync(transaction, outer_user.uid)
    assert stored_sync(transaction, child_user.uid)


@pytest.mark.asyncio
async def test_async_child_joined_to_finished_inner_expect_write_not_in_outer(
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
    unique_id: str,
) -> None:
    """안쪽 REQUIRES_NEW에 합친 자식 task가 안쪽이 끝난 뒤 쓰려 하면 거절되고, 바깥과 함께 commit되지 않는다."""
    outer_user = new_user(f"late_outer_{unique_id}")
    child_user = new_user(f"late_child_{unique_id}")
    child_joined = asyncio.Event()
    inner_finished = asyncio.Event()
    refused: list[type[BaseException]] = []

    async def child() -> None:
        async with async_transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            await inner_finished.wait()
            with pytest.raises(TransactionAlreadyFinishedError) as raised:
                async_transaction.session.add(schema_registry.from_domain(child_user))
            refused.append(raised.type)

    async with async_transaction.scope():
        async_transaction.session.add(schema_registry.from_domain(outer_user))
        async with async_transaction.scope(Propagation.REQUIRES_NEW):
            task = asyncio.create_task(child())
            await child_joined.wait()
        inner_finished.set()
        with pytest.raises(TransactionAlreadyFinishedError):
            await task

    assert refused == [TransactionAlreadyFinishedError]
    assert await stored(async_transaction, outer_user.uid)
    assert not await stored(async_transaction, child_user.uid)


def test_sync_thread_joined_to_finished_inner_expect_write_not_in_outer(
    schema_registry: SchemaRegistry,
    transaction: Transaction,
    unique_id: str,
) -> None:
    """안쪽 REQUIRES_NEW에 합친 thread가 안쪽이 끝난 뒤 쓰려 하면 거절되고, 바깥과 함께 commit되지 않는다."""
    outer_user = new_user(f"late_sync_outer_{unique_id}")
    child_user = new_user(f"late_sync_child_{unique_id}")
    child_joined = threading.Event()
    inner_finished = threading.Event()
    refused: list[type[BaseException]] = []

    def child() -> None:
        with transaction.scope(Propagation.REQUIRED):
            child_joined.set()
            inner_finished.wait()
            with pytest.raises(TransactionAlreadyFinishedError) as raised:
                transaction.session.add(schema_registry.from_domain(child_user))
            refused.append(raised.type)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.scope():
            transaction.session.add(schema_registry.from_domain(outer_user))
            with transaction.scope(Propagation.REQUIRES_NEW):
                future = executor.submit(copy_context().run, child)
                child_joined.wait()
            inner_finished.set()
            with pytest.raises(TransactionAlreadyFinishedError):
                future.result()

    assert refused == [TransactionAlreadyFinishedError]
    assert stored_sync(transaction, outer_user.uid)
    assert not stored_sync(transaction, child_user.uid)
