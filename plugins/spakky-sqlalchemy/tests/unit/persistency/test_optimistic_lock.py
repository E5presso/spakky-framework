"""Optimistic locking of generic repositories against a real SQLite database."""

from collections.abc import Generator
from pathlib import Path
from typing import Any, Self
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.repository import VersionConflictError
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from sqlalchemy import (
    Engine,
    Integer,
    String,
    Uuid,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from spakky.plugins.sqlalchemy.persistency.repository import AbstractGenericRepository
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@mutable
class Account(AbstractAggregateRoot[UUID]):
    """Aggregate whose balance is changed by competing use cases."""

    owner: str
    balance: int

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()


@Table(Account)
class AccountTable(AbstractMappableTable[Account]):
    """Versioned table: gets `version_id_col` from the mappable base."""

    __tablename__ = "optimistic_lock_accounts"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    owner: Mapped[str] = mapped_column(String(), nullable=False)
    balance: Mapped[int] = mapped_column(Integer(), nullable=False)

    @classmethod
    def from_domain(cls, domain: Account) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            owner=domain.owner,
            balance=domain.balance,
        )

    def to_domain(self) -> Account:
        return Account(
            uid=self.uid,
            version=self.version,
            owner=self.owner,
            balance=self.balance,
        )


@mutable
class Counter(AbstractAggregateRoot[UUID]):
    """Aggregate stored in a table that opted out of optimistic locking."""

    count: int

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()


@Table(Counter)
class CounterTable(AbstractMappableTable[Counter]):
    """Table whose own `__mapper_args__` replaces the versioned default."""

    __tablename__ = "optimistic_lock_counters"
    __mapper_args__: dict[str, Any] = {}  # Any: SQLAlchemy mapper kwargs

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    count: Mapped[int] = mapped_column(Integer(), nullable=False)

    @classmethod
    def from_domain(cls, domain: Counter) -> Self:
        return cls(uid=domain.uid, version=domain.version, count=domain.count)

    def to_domain(self) -> Counter:
        return Counter(uid=self.uid, version=self.version, count=self.count)


class AccountRepository(AbstractGenericRepository[Account, UUID]):
    """Repository under test for the versioned table."""


class CounterRepository(AbstractGenericRepository[Counter, UUID]):
    """Repository under test for the unversioned table."""


@pytest.fixture(name="engine")
def engine_fixture(tmp_path: Path) -> Generator[Engine, None, None]:
    """File-backed SQLite engine so that independent sessions see each other."""
    engine = create_engine(f"sqlite:///{tmp_path / 'optimistic_lock.db'}")
    tables = AccountTable.metadata.tables
    AccountTable.metadata.create_all(
        engine,
        tables=[
            tables[AccountTable.__tablename__],
            tables[CounterTable.__tablename__],
        ],
    )
    yield engine
    engine.dispose()


def _session_manager(session: Session) -> SessionManager:
    manager = MagicMock(spec=SessionManager)
    type(manager).session = PropertyMock(return_value=session)
    return manager


def _schema_registry() -> SchemaRegistry:
    registry = MagicMock(spec=SchemaRegistry)
    tables: dict[type, type[AbstractMappableTable[Any]]] = {
        Account: AccountTable,
        Counter: CounterTable,
    }
    registry.get_type.side_effect = tables.__getitem__
    registry.from_domain.side_effect = lambda domain: tables[type(domain)].from_domain(
        domain
    )
    return registry


def _accounts(session: Session) -> AccountRepository:
    return AccountRepository(
        _session_manager(session), _schema_registry(), AggregateCollector()
    )


def _counters(session: Session) -> CounterRepository:
    return CounterRepository(
        _session_manager(session), _schema_registry(), AggregateCollector()
    )


def _open_account(engine: Engine, balance: int = 100) -> Account:
    account = Account(uid=Account.next_id(), owner="alice", balance=balance)
    with Session(engine) as session, session.begin():
        _accounts(session).save(account)
    return account


def _stored_account(engine: Engine, uid: UUID) -> AccountTable:
    with Session(engine) as session:
        return session.execute(
            select(AccountTable).where(AccountTable.uid == uid)
        ).scalar_one()


def _write_concurrently_before_flush(
    session: Session, engine: Engine, uid: UUID, balance: int
) -> None:
    """Commit a competing write after `session` compared versions, before its UPDATE."""

    def competing_write(*_: object) -> None:
        with Session(engine) as competitor, competitor.begin():
            repository = _accounts(competitor)
            winner = repository.get(uid)
            winner.balance = balance
            repository.save(winner)

    event.listen(session, "before_flush", competing_write, once=True)


def test_versioned_table_mapper_expect_version_id_col_without_generator() -> None:
    """애그리거트 테이블의 version 컬럼이 version_id_col로, generator는 False로 매핑된다."""
    mapper = inspect(AccountTable)

    assert mapper.version_id_col is AccountTable.__table__.c.version
    assert mapper.version_id_generator is False


def test_save_new_aggregate_expect_inserted_with_current_version(
    engine: Engine,
) -> None:
    """새 애그리거트를 save하면 현재 version으로 INSERT된다."""
    account = Account(uid=Account.next_id(), owner="alice", balance=100)
    account.balance = 150

    with Session(engine) as session, session.begin():
        saved = _accounts(session).save(account)

    stored = _stored_account(engine, account.uid)
    assert stored.balance == 150
    assert stored.version == account.version
    assert saved.version == account.version
    assert account.persisted_version == account.version


def test_save_loaded_aggregate_after_change_expect_updated(engine: Engine) -> None:
    """다른 writer가 없으면 불러온 애그리거트의 변경이 정상 저장된다."""
    uid = _open_account(engine).uid

    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        account = repository.get(uid)
        loaded_version = account.version
        account.balance = 70
        repository.save(account)

    stored = _stored_account(engine, uid)
    assert stored.balance == 70
    assert stored.version == account.version
    assert stored.version != loaded_version


def test_save_from_two_sessions_expect_second_version_conflict(
    engine: Engine,
) -> None:
    """두 세션이 같은 행을 읽고 모두 저장하면 두 번째 저장이 VersionConflictError로 실패한다."""
    uid = _open_account(engine).uid

    with (
        Session(engine, expire_on_commit=False) as first_session,
        Session(engine, expire_on_commit=False) as second_session,
    ):
        first = _accounts(first_session)
        second = _accounts(second_session)
        first_account = first.get(uid)
        second_account = second.get(uid)
        first_session.commit()
        second_session.commit()

        first_account.balance = 10
        first.save(first_account)
        first_session.commit()

        second_account.balance = 20
        with pytest.raises(VersionConflictError):
            second.save(second_account)
        second_session.rollback()

    stored = _stored_account(engine, uid)
    assert stored.balance == 10
    assert stored.version == first_account.version


def test_save_instance_with_old_version_expect_version_conflict(
    engine: Engine,
) -> None:
    """오래된 version을 들고 있는 인스턴스를 새 세션에서 저장하면 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid
    with Session(engine) as session:
        stale = _accounts(session).get(uid)
    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        winner = repository.get(uid)
        winner.balance = 1
        repository.save(winner)

    stale.balance = 2
    with Session(engine) as session:
        with pytest.raises(VersionConflictError):
            _accounts(session).save(stale)

    assert _stored_account(engine, uid).balance == 1


def test_save_same_instance_twice_expect_both_updates_stored(engine: Engine) -> None:
    """한 인스턴스를 연속으로 두 번 저장해도 두 번 모두 성공한다."""
    uid = _open_account(engine).uid

    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        account = repository.get(uid)
        account.balance = 60
        repository.save(account)
        first_saved_version = account.version
        account.balance = 30
        repository.save(account)

    stored = _stored_account(engine, uid)
    assert stored.balance == 30
    assert stored.version == account.version
    assert stored.version != first_saved_version


def test_save_same_instance_in_later_session_expect_updated(engine: Engine) -> None:
    """저장에 성공한 인스턴스를 다음 트랜잭션에서 다시 변경·저장해도 성공한다."""
    account = _open_account(engine)

    account.balance = 5
    with Session(engine) as session, session.begin():
        _accounts(session).save(account)

    assert _stored_account(engine, account.uid).balance == 5


def test_save_all_with_stale_instance_expect_version_conflict(engine: Engine) -> None:
    """save_all에 오래된 인스턴스가 섞여 있으면 VersionConflictError가 발생하고 아무것도 반영되지 않는다."""
    fresh_uid = _open_account(engine, balance=100).uid
    stale_uid = _open_account(engine, balance=200).uid

    with (
        Session(engine, expire_on_commit=False) as first_session,
        Session(engine, expire_on_commit=False) as second_session,
    ):
        first = _accounts(first_session)
        second = _accounts(second_session)
        fresh = first.get(fresh_uid)
        stale = first.get(stale_uid)
        first_session.commit()
        winner = second.get(stale_uid)
        winner.balance = 201
        second.save(winner)
        second_session.commit()

        fresh.balance = 101
        stale.balance = 202
        with pytest.raises(VersionConflictError):
            first.save_all([fresh, stale])
        first_session.rollback()

    assert _stored_account(engine, fresh_uid).balance == 100
    assert _stored_account(engine, stale_uid).balance == 201


def test_save_all_instance_with_old_version_expect_version_conflict(
    engine: Engine,
) -> None:
    """오래된 version의 인스턴스를 새 세션에서 save_all하면 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid
    with Session(engine) as session:
        stale = _accounts(session).get(uid)
    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        winner = repository.get(uid)
        winner.balance = 1
        repository.save(winner)

    stale.balance = 2
    with Session(engine) as session:
        with pytest.raises(VersionConflictError):
            _accounts(session).save_all([stale])

    assert _stored_account(engine, uid).balance == 1


def test_save_all_loaded_aggregates_expect_all_updated(engine: Engine) -> None:
    """save_all이 불러온 애그리거트 여러 개의 변경을 모두 저장하고 재저장도 가능하다."""
    uids = [_open_account(engine).uid, _open_account(engine).uid]

    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        accounts = list(repository.range(uids))
        for account in accounts:
            account.balance = 7
        repository.save_all(accounts)
        for account in accounts:
            account.balance = 8
        repository.save_all(accounts)

    assert [_stored_account(engine, uid).balance for uid in uids] == [8, 8]


def test_delete_changed_aggregate_expect_row_removed(engine: Engine) -> None:
    """불러온 뒤 변경한 애그리거트도 다른 writer가 없으면 삭제된다."""
    uid = _open_account(engine).uid

    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        account = repository.get(uid)
        account.balance = 0
        repository.delete(account)

    with Session(engine) as session:
        assert session.get(AccountTable, uid) is None


def test_delete_from_two_sessions_expect_stale_delete_version_conflict(
    engine: Engine,
) -> None:
    """다른 세션이 먼저 변경한 행을 삭제하려 하면 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid

    with (
        Session(engine, expire_on_commit=False) as first_session,
        Session(engine, expire_on_commit=False) as second_session,
    ):
        first = _accounts(first_session)
        second = _accounts(second_session)
        doomed = first.get(uid)
        first_session.commit()
        winner = second.get(uid)
        winner.balance = 999
        second.save(winner)
        second_session.commit()

        with pytest.raises(VersionConflictError):
            first.delete(doomed)
        first_session.rollback()

    assert _stored_account(engine, uid).balance == 999


def test_delete_all_from_two_sessions_expect_stale_delete_version_conflict(
    engine: Engine,
) -> None:
    """delete_all도 다른 세션이 먼저 변경한 행에 대해 VersionConflictError를 발생시킨다."""
    uid = _open_account(engine).uid

    with (
        Session(engine, expire_on_commit=False) as first_session,
        Session(engine, expire_on_commit=False) as second_session,
    ):
        first = _accounts(first_session)
        second = _accounts(second_session)
        doomed = first.get(uid)
        first_session.commit()
        winner = second.get(uid)
        winner.balance = 999
        second.save(winner)
        second_session.commit()

        with pytest.raises(VersionConflictError):
            first.delete_all([doomed])
        first_session.rollback()

    assert _stored_account(engine, uid).balance == 999


def test_delete_all_instance_with_old_version_expect_version_conflict(
    engine: Engine,
) -> None:
    """오래된 version의 인스턴스를 새 세션에서 delete_all하면 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid
    with Session(engine) as session:
        stale = _accounts(session).get(uid)
    with Session(engine) as session, session.begin():
        repository = _accounts(session)
        winner = repository.get(uid)
        winner.balance = 1
        repository.save(winner)

    with Session(engine) as session:
        with pytest.raises(VersionConflictError):
            _accounts(session).delete_all([stale])

    assert _stored_account(engine, uid).balance == 1


def test_save_to_table_without_version_check_expect_last_write_wins(
    engine: Engine,
) -> None:
    """__mapper_args__로 version 검사를 끈 테이블은 오래된 인스턴스 저장도 덮어쓴다."""
    counter = Counter(uid=Counter.next_id(), count=0)
    with Session(engine) as session, session.begin():
        _counters(session).save(counter)
    with Session(engine) as session:
        stale = _counters(session).get(counter.uid)
    with Session(engine) as session, session.begin():
        repository = _counters(session)
        winner = repository.get(counter.uid)
        winner.count = 1
        repository.save_all([winner])

    stale.count = 2
    with Session(engine) as session, session.begin():
        _counters(session).save(stale)

    assert inspect(CounterTable).version_id_col is None
    with Session(engine) as session:
        stored = session.get(CounterTable, counter.uid)
        assert stored is not None
        assert stored.count == 2


def test_save_racing_writer_between_compare_and_update_expect_version_conflict(
    engine: Engine,
) -> None:
    """merge의 version 비교 이후 UPDATE 직전에 다른 writer가 커밋하면 UPDATE가 0행이 되어 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid

    with Session(engine) as session:
        repository = _accounts(session)
        account = repository.get(uid)
        account.balance = 20
        _write_concurrently_before_flush(session, engine, uid, balance=10)
        with pytest.raises(VersionConflictError):
            repository.save(account)
        session.rollback()

    assert _stored_account(engine, uid).balance == 10


def test_save_all_racing_writer_between_compare_and_update_expect_version_conflict(
    engine: Engine,
) -> None:
    """save_all의 일괄 flush 직전에 다른 writer가 커밋하면 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid

    with Session(engine) as session:
        repository = _accounts(session)
        account = repository.get(uid)
        account.balance = 20
        _write_concurrently_before_flush(session, engine, uid, balance=10)
        with pytest.raises(VersionConflictError):
            repository.save_all([account])
        session.rollback()

    assert _stored_account(engine, uid).balance == 10


def test_delete_all_racing_writer_between_compare_and_delete_expect_version_conflict(
    engine: Engine,
) -> None:
    """delete_all의 일괄 flush 직전에 다른 writer가 커밋하면 DELETE가 0행이 되어 VersionConflictError가 발생한다."""
    uid = _open_account(engine).uid

    with Session(engine) as session:
        repository = _accounts(session)
        account = repository.get(uid)
        _write_concurrently_before_flush(session, engine, uid, balance=10)
        with pytest.raises(VersionConflictError):
            repository.delete_all([account])
        session.rollback()

    assert _stored_account(engine, uid).balance == 10
