"""Unit tests for the SQLAlchemy processed-event store (inbox)."""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import spakky.event
import spakky.plugins.sqlalchemy
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.event.idempotency import ProcessedEventKey
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.contributions.event import initialize
from spakky.plugins.sqlalchemy.event.store import (
    AsyncSqlAlchemyProcessedEventStore,
    DuplicateProcessedEventError,
    SqlAlchemyProcessedEventStore,
)
from spakky.plugins.sqlalchemy.event.table import ProcessedEventTable
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)


@dataclass(slots=True)
class SessionManagerStub:
    """Minimal session manager shape used by store unit tests."""

    session: Session


class AsyncSessionFacade:
    """Async call surface over a sync SQLite session.

    No async SQLite driver is installed, so the async store is exercised
    through this facade here and against PostgreSQL in the integration tests.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get(self, entity: type[ProcessedEventTable], ident: Any) -> Any:
        return self._session.get(entity, ident)

    def add(self, instance: object) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()

    async def execute(self, statement: Any) -> Any:
        return self._session.execute(statement)


@dataclass(slots=True)
class AsyncSessionManagerStub:
    """Minimal async session manager shape used by store unit tests."""

    session: AsyncSessionFacade


@pytest.fixture(name="engine")
def engine_fixture() -> Generator[Engine, None, None]:
    """Create an isolated in-memory SQLite database with the inbox table."""
    engine = create_engine("sqlite:///:memory:")
    ProcessedEventTable.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine: Engine) -> Generator[Session, None, None]:
    """Open one session standing in for the handler's transaction."""
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def key(
    handler: str = "Billing.charge", subscriber: str = "billing"
) -> ProcessedEventKey:
    return ProcessedEventKey(subscriber=subscriber, handler=handler, event_id=uuid4())


def sync_store(session: Session) -> SqlAlchemyProcessedEventStore:
    return SqlAlchemyProcessedEventStore(
        cast(SessionManager, SessionManagerStub(session=session))
    )


def async_store(session: Session) -> AsyncSqlAlchemyProcessedEventStore:
    return AsyncSqlAlchemyProcessedEventStore(
        cast(
            AsyncSessionManager,
            AsyncSessionManagerStub(session=AsyncSessionFacade(session)),
        )
    )


def test_store_record_expect_visible_in_same_transaction_and_scoped_by_key(
    session: Session,
) -> None:
    """기록은 같은 트랜잭션 안에서 바로 보이고, 구독자·처리기별로 구분된다."""
    store = sync_store(session)
    first = key()
    assert store.exists(first) is False

    store.record(first)

    assert store.exists(first) is True
    assert (
        store.exists(first.model_copy(update={"handler": "Billing.receipt"})) is False
    )
    assert store.exists(first.model_copy(update={"subscriber": ""})) is False


def test_store_record_rollback_expect_record_gone_with_handler_changes(
    session: Session,
) -> None:
    """처리기 트랜잭션이 되돌려지면 처리 기록도 함께 사라진다."""
    store = sync_store(session)
    first = key()
    store.record(first)

    session.rollback()

    assert store.exists(first) is False


def test_store_record_concurrent_duplicate_expect_second_rejected(
    engine: Engine, session: Session
) -> None:
    """다른 전달이 먼저 커밋한 같은 이벤트는 두 번째 기록에서 거부된다."""
    first = key()
    with sessionmaker(bind=engine)() as other:
        sync_store(other).record(first)
        other.commit()
    with pytest.raises(DuplicateProcessedEventError) as caught:
        sync_store(session).record(first)
    assert caught.value.key == first


def test_store_purge_expect_only_old_records_removed(session: Session) -> None:
    """보존 기간이 지난 기록만 지운다."""
    store = sync_store(session)
    old, recent = key(), key()
    store.record(old)
    store.record(recent)
    now = datetime.now(UTC)
    session.get_one(
        ProcessedEventTable, (old.subscriber, old.handler, old.event_id)
    ).processed_at = now - timedelta(days=30)
    session.flush()

    assert store.purge(now - timedelta(days=7)) == 1
    assert store.exists(old) is False
    assert store.exists(recent) is True
    assert len(session.scalars(select(ProcessedEventTable)).all()) == 1


def test_store_purge_without_dml_result_expect_zero() -> None:
    """행 수를 알려 주지 않는 실행 결과는 0으로 보고한다."""
    manager = MagicMock()
    manager.session.execute.return_value = object()
    store = SqlAlchemyProcessedEventStore(cast(SessionManager, manager))
    assert store.purge(datetime.now(UTC)) == 0


async def test_async_store_expect_same_contract_as_sync(
    engine: Engine, session: Session
) -> None:
    """비동기 저장소도 기록·조회·중복 거부·보존 정리를 같은 방식으로 한다."""
    store = async_store(session)
    first, old = key(), key()
    assert await store.exists(first) is False
    await store.record(first)
    await store.record(old)
    assert await store.exists(first) is True

    now = datetime.now(UTC)
    session.get_one(
        ProcessedEventTable, (old.subscriber, old.handler, old.event_id)
    ).processed_at = now - timedelta(days=30)
    session.flush()
    assert await store.purge(now - timedelta(days=7)) == 1
    session.commit()

    with sessionmaker(bind=engine)() as other:
        with pytest.raises(DuplicateProcessedEventError):
            await async_store(other).record(first)


async def test_async_store_purge_without_dml_result_expect_zero() -> None:
    """비동기에서도 행 수 없는 실행 결과는 0으로 보고한다."""

    class NoRowCountSession:
        async def execute(self, statement: object) -> object:
            return object()

    manager = MagicMock()
    manager.session = NoRowCountSession()
    store = AsyncSqlAlchemyProcessedEventStore(cast(AsyncSessionManager, manager))
    assert await store.purge(datetime.now(UTC)) == 0


@pytest.mark.parametrize("asynchronous", [True, False])
def test_event_contribution_expect_table_and_stores_registered(
    monkeypatch: pytest.MonkeyPatch, asynchronous: bool
) -> None:
    """event contribution은 inbox 테이블과 저장소를 등록하고, 비동기는 설정을 따른다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", str(asynchronous).lower())
    app = MagicMock()

    initialize(app)

    added = [call.args[0] for call in app.add.call_args_list]
    assert added[:2] == [ProcessedEventTable, SqlAlchemyProcessedEventStore]
    assert (AsyncSqlAlchemyProcessedEventStore in added) is asynchronous


def test_event_contribution_entry_point_expect_declared() -> None:
    """SQLAlchemy event contribution entry point metadata를 검증한다."""
    assert any(
        entry_point.name == "spakky-sqlalchemy"
        and entry_point.value
        == "spakky.plugins.sqlalchemy.contributions.event:initialize"
        for entry_point in entry_points(group="spakky.contributions.spakky.event")
    )


@pytest.mark.parametrize("with_event", [True, False])
def test_load_plugins_expect_event_contribution_follows_event_plugin(
    monkeypatch: pytest.MonkeyPatch, with_event: bool
) -> None:
    """spakky-event가 active일 때만 inbox 저장소가 등록된다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
        "postgresql+psycopg://test:test@localhost/test",
    )
    include = {spakky.plugins.sqlalchemy.PLUGIN_NAME}
    if with_event:
        include.add(spakky.event.PLUGIN_NAME)

    app = SpakkyApplication(ApplicationContext()).load_plugins(include=include)

    added_types = {pod.type_ for pod in app.container.pods.values()}
    assert (SqlAlchemyProcessedEventStore in added_types) is with_event
