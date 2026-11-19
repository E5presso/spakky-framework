"""Unit tests for session managers."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.data.persistency.error import TransactionAlreadyFinishedError
from spakky.data.persistency.transaction import PhysicalTransaction
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
    SessionNotBoundError,
    SessionNotInitializedError,
)


def test_session_manager_init_stores_engine() -> None:
    """SessionManager가 초기화 시 engine을 저장하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    manager = SessionManager(mock_connection_manager)

    assert manager._engine is mock_engine
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_session_before_open_raises_error() -> None:
    """open() 전에 session 접근 시 SessionNotInitializedError가 발생함을 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    manager = SessionManager(mock_connection_manager)

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_set_application_context_creates_session_factory() -> None:
    """set_application_context가 session factory를 만드는지 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)

    assert manager._session_factory is not None


def test_session_manager_open_creates_session() -> None:
    """open()이 session을 생성하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open(PhysicalTransaction())

    assert manager.session is not None
    manager.close()


def test_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open(PhysicalTransaction())
    manager.close()

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.close()  # Should not raise


def test_session_manager_session_property_returns_session() -> None:
    """session property가 Session 객체를 반환하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open(PhysicalTransaction())

    from sqlalchemy.orm import Session

    assert isinstance(manager.session, Session)
    manager.close()


# --- Async Session Manager Tests ---


def test_async_session_manager_init_stores_engine() -> None:
    """AsyncSessionManager가 초기화 시 engine을 저장하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    manager = AsyncSessionManager(mock_connection_manager)

    assert manager._engine is mock_engine
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_async_session_manager_session_before_open_raises_error() -> None:
    """open() 전에 session 접근 시 SessionNotInitializedError가 발생함을 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    manager = AsyncSessionManager(mock_connection_manager)

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_async_session_manager_set_application_context_creates_session_factory() -> (
    None
):
    """set_application_context가 async session factory를 만드는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)

    assert manager._session_factory is not None


@pytest.mark.asyncio
async def test_async_session_manager_open_creates_session() -> None:
    """open()이 session을 생성하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open(PhysicalTransaction())

    assert manager.session is not None
    await manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open(PhysicalTransaction())
    await manager.close()

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


@pytest.mark.asyncio
async def test_async_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.close()  # Should not raise


@pytest.mark.asyncio
async def test_async_session_manager_session_property_returns_session() -> None:
    """session property가 AsyncSession 객체를 반환하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open(PhysicalTransaction())

    # session property를 통해 접근해야 return 라인이 실행됨
    session = manager.session
    assert session is not None
    await manager.close()


def test_unbound_sync_session_rejects_open_and_accepts_cleanup() -> None:
    """컨텍스트 주입 전에는 열기를 거절하고 정리는 안전하게 끝낸다."""
    manager = SessionManager(MagicMock(spec=ConnectionManager))
    with pytest.raises(SessionNotInitializedError):
        manager.open(PhysicalTransaction())
    manager.close()


@pytest.mark.asyncio
async def test_unbound_async_session_rejects_open_and_accepts_cleanup() -> None:
    """비동기 매니저도 컨텍스트 주입 전 자원을 생성하지 않는다."""
    manager = AsyncSessionManager(MagicMock(spec=AsyncConnectionManager))
    with pytest.raises(SessionNotInitializedError):
        await manager.open(PhysicalTransaction())
    await manager.close()


def test_shared_sync_manager_keeps_overlapping_contexts_independent() -> None:
    """한 매니저를 공유해도 다른 컨텍스트의 close가 원래 세션을 닫지 않는다."""
    from contextvars import copy_context
    from sqlalchemy import create_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    context = ApplicationContext()
    manager.set_application_context(context)
    manager.open(PhysicalTransaction())
    first = manager.session
    other = copy_context()
    other.run(context.clear_context)
    other.run(manager.open, PhysicalTransaction())
    assert other.run(lambda: manager.session) is not first
    assert manager.session is first
    other.run(manager.close)
    assert manager.session is first
    manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    connection.connection.dispose()


@pytest.mark.asyncio
async def test_shared_async_manager_keeps_overlapping_contexts_independent() -> None:
    """비동기 요청 사이에서도 현재 컨텍스트의 세션만 조회·종료한다."""
    import asyncio
    from contextvars import Context
    from sqlalchemy.ext.asyncio import create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    context = ApplicationContext()
    manager.set_application_context(context)
    await manager.open(PhysicalTransaction())
    first = manager.session

    async def other_request() -> None:
        context.clear_context()
        await manager.open(PhysicalTransaction())
        assert manager.session is not first
        await manager.close()
        with pytest.raises(SessionNotInitializedError):
            _ = manager.session

    # 다른 요청은 이 요청의 context를 이어받지 않은 별도 task다.
    await asyncio.create_task(other_request(), context=Context())
    assert manager.session is first
    await manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    await connection.connection.dispose()


def test_sync_session_manager_nested_open_expect_stack_restores_outer() -> None:
    """open()을 겹쳐 부르면 위의 새 session을 쓰고, close()하면 바깥 session으로 돌아간다."""
    from sqlalchemy import create_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())
    manager.open(PhysicalTransaction())
    outer = manager.session
    manager.open(PhysicalTransaction())
    inner = manager.session

    assert inner is not outer
    manager.close()
    assert manager.session is outer
    manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_nested_open_expect_stack_restores_outer() -> None:
    """비동기에서도 겹친 open()은 새 session을 쌓고, close()하면 바깥으로 돌아간다."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())
    await manager.open(PhysicalTransaction())
    outer = manager.session
    await manager.open(PhysicalTransaction())
    inner = manager.session

    assert inner is not outer
    await manager.close()
    assert manager.session is outer
    await manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    await connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_concurrent_child_tasks_expect_own_sessions() -> (
    None
):
    """같은 요청의 자식 task 둘이 동시에 open()해도 서로의 session을 쓰거나 닫지 않는다."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())
    await manager.open(PhysicalTransaction())
    outer = manager.session
    a_opened = asyncio.Event()
    b_opened = asyncio.Event()
    a_closed = asyncio.Event()
    seen: dict[str, tuple[AsyncSession, AsyncSession, AsyncSession]] = {}

    async def a() -> None:
        inherited = manager.session
        await manager.open(PhysicalTransaction())
        mine = manager.session
        a_opened.set()
        await b_opened.wait()
        seen["a"] = (inherited, mine, manager.session)
        await manager.close()
        a_closed.set()

    async def b() -> None:
        await a_opened.wait()
        inherited = manager.session
        await manager.open(PhysicalTransaction())
        mine = manager.session
        b_opened.set()
        await a_closed.wait()
        seen["b"] = (inherited, mine, manager.session)
        await manager.close()

    await asyncio.gather(a(), b())

    assert seen["a"][0] is outer and seen["b"][0] is outer
    assert seen["a"][1] is seen["a"][2]
    assert seen["b"][1] is seen["b"][2]
    assert seen["a"][1] is not seen["b"][1]
    assert outer not in (seen["a"][1], seen["b"][1])
    assert manager.session is outer
    await manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    await connection.connection.dispose()


def test_sync_session_manager_concurrent_threads_expect_own_sessions() -> None:
    """context를 복사한 thread 둘이 동시에 open()해도 각자의 session만 쓰고 닫는다."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())
    manager.open(PhysicalTransaction())
    outer = manager.session
    barrier = threading.Barrier(2)
    seen: dict[str, tuple[Session, Session, Session]] = {}

    def child(name: str) -> None:
        inherited = manager.session
        manager.open(PhysicalTransaction())
        mine = manager.session
        barrier.wait()
        seen[name] = (inherited, mine, manager.session)
        barrier.wait()
        manager.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(copy_context().run, child, name) for name in "ab"]
        for future in futures:
            future.result()

    assert seen["a"][0] is outer and seen["b"][0] is outer
    assert seen["a"][1] is seen["a"][2]
    assert seen["b"][1] is seen["b"][2]
    assert seen["a"][1] is not seen["b"][1]
    assert manager.session is outer
    manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_child_task_after_finished_expect_refused_then_own() -> (
    None
):
    """끝난 transaction의 session은 그 뒤에 도는 자식 task에 내주지 않고, 새로 연 session만 쓴다."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())
    outer_tx = PhysicalTransaction()
    outer_finished = asyncio.Event()
    seen: list[AsyncSession] = []

    async def child() -> None:
        await outer_finished.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session
        await manager.open(PhysicalTransaction())
        seen.append(manager.session)
        await manager.close()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session

    await manager.open(outer_tx)
    outer = manager.session
    task = asyncio.create_task(child())
    outer_tx.finished = True
    outer_finished.set()
    await task
    await manager.close()

    assert len(seen) == 1
    assert seen[0] is not outer
    await connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_child_task_after_inner_finished_expect_refused() -> (
    None
):
    """끝난 안쪽 session 대신 아래 바깥 session을 내주지 않고, 바깥에 합쳐야만 바깥을 쓴다."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())
    outer_tx = PhysicalTransaction()
    inner_tx = PhysicalTransaction()
    inner_finished = asyncio.Event()
    seen: list[AsyncSession] = []

    async def child() -> None:
        await inner_finished.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session
        await manager.join(outer_tx)
        seen.append(manager.session)
        await manager.leave()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session

    await manager.open(outer_tx)
    outer = manager.session
    await manager.open(inner_tx)
    task = asyncio.create_task(child())
    inner_tx.finished = True
    inner_finished.set()
    await task
    await manager.close()

    assert seen == [outer]
    assert manager.session is outer
    await manager.close()
    await connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_join_unknown_transaction_expect_not_bound() -> (
    None
):
    """이 context에 session이 없는 transaction에 합치려 하면 SessionNotBoundError가 난다."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())
    await manager.open(PhysicalTransaction())

    with pytest.raises(SessionNotBoundError):
        await manager.join(PhysicalTransaction())

    await manager.close()
    await connection.connection.dispose()


@pytest.mark.asyncio
async def test_async_session_manager_leave_without_session_expect_not_initialized() -> (
    None
):
    """session이 없는데 leave()하면 SessionNotInitializedError가 난다."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    manager.set_application_context(ApplicationContext())

    with pytest.raises(SessionNotInitializedError):
        await manager.leave()

    await connection.connection.dispose()


def test_sync_session_manager_thread_after_finished_expect_refused_then_own() -> None:
    """끝난 transaction의 session은 그 뒤에 도는 thread에 내주지 않고, 새로 연 session만 쓴다."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())
    outer_tx = PhysicalTransaction()
    outer_finished = threading.Event()
    seen: list[Session] = []

    def child() -> None:
        outer_finished.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session
        manager.open(PhysicalTransaction())
        seen.append(manager.session)
        manager.close()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session

    manager.open(outer_tx)
    outer = manager.session
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(copy_context().run, child)
        outer_tx.finished = True
        outer_finished.set()
        future.result()
    manager.close()

    assert len(seen) == 1
    assert seen[0] is not outer
    connection.connection.dispose()


def test_sync_session_manager_thread_after_inner_finished_expect_refused() -> None:
    """끝난 안쪽 session 대신 아래 바깥 session을 내주지 않고, 바깥에 합쳐야만 바깥을 쓴다."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())
    outer_tx = PhysicalTransaction()
    inner_tx = PhysicalTransaction()
    inner_finished = threading.Event()
    seen: list[Session] = []

    def child() -> None:
        inner_finished.wait()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session
        manager.join(outer_tx)
        seen.append(manager.session)
        manager.leave()
        with pytest.raises(TransactionAlreadyFinishedError):
            _ = manager.session

    manager.open(outer_tx)
    outer = manager.session
    manager.open(inner_tx)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(copy_context().run, child)
        inner_tx.finished = True
        inner_finished.set()
        future.result()
    manager.close()

    assert seen == [outer]
    assert manager.session is outer
    manager.close()
    connection.connection.dispose()


def test_sync_session_manager_join_unknown_transaction_expect_not_bound() -> None:
    """이 context에 session이 없는 transaction에 합치려 하면 SessionNotBoundError가 난다."""
    from sqlalchemy import create_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())
    manager.open(PhysicalTransaction())

    with pytest.raises(SessionNotBoundError):
        manager.join(PhysicalTransaction())

    manager.close()
    connection.connection.dispose()


def test_sync_session_manager_leave_without_session_expect_not_initialized() -> None:
    """session이 없는데 leave()하면 SessionNotInitializedError가 난다."""
    from sqlalchemy import create_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    manager.set_application_context(ApplicationContext())

    with pytest.raises(SessionNotInitializedError):
        manager.leave()

    connection.connection.dispose()
