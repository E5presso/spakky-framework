"""Unique-key collisions of new aggregates against a real SQLite database."""

from collections.abc import Generator
from pathlib import Path
from typing import Self
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.repository import (
    EntityAlreadyExistsError,
    VersionConflictError,
)
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from sqlalchemy import Engine, String, Uuid, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)


@mutable
class Member(AbstractAggregateRoot[UUID]):
    """Aggregate with a unique email besides its identifier."""

    email: str
    nickname: str | None = None  # None: not chosen yet; the table requires one

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()


@Table(Member)
class MemberTable(AbstractMappableTable[Member]):
    """Versioned table with a unique key that is not the primary key."""

    __tablename__ = "already_exists_members"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    email: Mapped[str] = mapped_column(String(), nullable=False, unique=True)
    nickname: Mapped[str] = mapped_column(String(), nullable=False)

    @classmethod
    def from_domain(cls, domain: Member) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            email=domain.email,
            nickname=domain.nickname,
        )

    def to_domain(self) -> Member:
        return Member(
            uid=self.uid,
            version=self.version,
            email=self.email,
            nickname=self.nickname,
        )


class MemberRepository(AbstractGenericRepository[Member, UUID]):
    """Sync repository under test."""


class AsyncMemberRepository(AbstractAsyncGenericRepository[Member, UUID]):
    """Async repository under test."""


class _DriverError(Exception):
    """Stand-in for a DBAPI driver error carrying driver-specific codes."""

    def __init__(self, **codes: str) -> None:
        super().__init__("driver error")
        for name, value in codes.items():
            setattr(self, name, value)


@pytest.fixture(name="engine")
def engine_fixture(tmp_path: Path) -> Generator[Engine, None, None]:
    """File-backed SQLite engine so that independent sessions see each other."""
    engine = create_engine(f"sqlite:///{tmp_path / 'already_exists.db'}")
    MemberTable.metadata.create_all(
        engine, tables=[MemberTable.metadata.tables[MemberTable.__tablename__]]
    )
    yield engine
    engine.dispose()


def _schema_registry() -> SchemaRegistry:
    registry = MagicMock(spec=SchemaRegistry)
    registry.get_type.return_value = MemberTable
    registry.from_domain.side_effect = MemberTable.from_domain
    return registry


def _members(session: Session) -> MemberRepository:
    manager = MagicMock(spec=SessionManager)
    type(manager).session = PropertyMock(return_value=session)
    return MemberRepository(manager, _schema_registry(), AggregateCollector())


def _async_members(session: MagicMock) -> AsyncMemberRepository:
    manager = MagicMock(spec=AsyncSessionManager)
    type(manager).session = PropertyMock(return_value=session)
    return AsyncMemberRepository(manager, _schema_registry(), AggregateCollector())


def _member(email: str, nickname: str | None = "nick") -> Member:
    return Member(uid=Member.next_id(), email=email, nickname=nickname)


def _join(engine: Engine, email: str) -> Member:
    member = _member(email)
    with Session(engine) as session, session.begin():
        _members(session).save(member)
    return member


def _integrity_error(statement: str | None, **codes: str) -> IntegrityError:
    return IntegrityError(statement, None, _DriverError(**codes))


def _insert_unique_violation() -> IntegrityError:
    return _integrity_error("INSERT INTO already_exists_members", sqlstate="23505")


def _async_session(merged_pending: bool) -> MagicMock:
    session = MagicMock()
    merged = MagicMock()
    merged._sa_instance_state.pending = merged_pending
    session.merge = AsyncMock(return_value=merged)
    session.flush = AsyncMock()
    return session


def test_save_new_aggregate_with_taken_unique_key_expect_already_exists(
    engine: Engine,
) -> None:
    """다른 집합체가 가진 유일 키로 새 집합체를 저장하면 EntityAlreadyExistsError가 난다."""
    _join(engine, "alice@example.com")
    duplicate = _member("alice@example.com")

    with Session(engine) as session, pytest.raises(EntityAlreadyExistsError) as error:
        _members(session).save(duplicate)

    assert error.value.args == (duplicate.uid,)
    assert isinstance(error.value.__cause__, IntegrityError)
    assert not isinstance(error.value, VersionConflictError)


def test_save_new_aggregate_created_concurrently_with_same_id_expect_already_exists(
    engine: Engine,
) -> None:
    """두 작업 단위가 같은 식별자의 새 집합체를 함께 만들면 늦은 쪽이 EntityAlreadyExistsError를 받는다."""
    late = _member("late@example.com")

    def competing_insert(*_: object) -> None:
        with Session(engine) as competitor, competitor.begin():
            _members(competitor).save(
                Member(uid=late.uid, email="early@example.com", nickname="early")
            )

    with Session(engine) as session, pytest.raises(EntityAlreadyExistsError):
        event.listen(session, "before_flush", competing_insert, once=True)
        _members(session).save(late)


def test_save_loaded_aggregate_into_taken_unique_key_expect_integrity_error(
    engine: Engine,
) -> None:
    """기존 행의 UPDATE에서 난 유일 위반은 EntityAlreadyExistsError로 바꾸지 않는다."""
    _join(engine, "alice@example.com")
    bob = _join(engine, "bob@example.com")

    with Session(engine) as session, pytest.raises(IntegrityError):
        repository = _members(session)
        loaded = repository.get(bob.uid)
        loaded.email = "alice@example.com"
        repository.save(loaded)


def test_save_new_aggregate_violating_not_null_expect_integrity_error(
    engine: Engine,
) -> None:
    """새 집합체 INSERT의 유일 위반이 아닌 무결성 오류는 그대로 올린다."""
    with Session(engine) as session, pytest.raises(IntegrityError):
        _members(session).save(_member("carol@example.com", nickname=None))


def test_save_all_with_new_duplicate_flushed_last_expect_already_exists(
    engine: Engine,
) -> None:
    """save_all의 마지막 flush에서 새 집합체가 유일 키와 부딪히면 새 집합체 식별자 목록을 담아 알린다."""
    _join(engine, "alice@example.com")
    duplicate = _member("alice@example.com")

    with Session(engine) as session, pytest.raises(EntityAlreadyExistsError) as error:
        _members(session).save_all([duplicate])

    assert error.value.args == ([duplicate.uid],)


def test_save_all_with_new_duplicate_flushed_by_next_merge_expect_already_exists(
    engine: Engine,
) -> None:
    """save_all 도중 다음 집합체의 merge가 앞선 새 집합체를 flush하다 부딪혀도 EntityAlreadyExistsError다."""
    _join(engine, "alice@example.com")
    duplicate = _member("alice@example.com")
    other = _member("dave@example.com")

    with Session(engine) as session, pytest.raises(EntityAlreadyExistsError) as error:
        _members(session).save_all([duplicate, other])

    assert error.value.args == ([duplicate.uid],)


def test_save_all_loaded_aggregate_into_taken_unique_key_expect_integrity_error(
    engine: Engine,
) -> None:
    """save_all에 새 집합체가 없으면 UPDATE의 유일 위반을 그대로 올린다."""
    _join(engine, "alice@example.com")
    bob = _join(engine, "bob@example.com")

    with Session(engine) as session, pytest.raises(IntegrityError):
        repository = _members(session)
        loaded = repository.get(bob.uid)
        loaded.email = "alice@example.com"
        repository.save_all([loaded])


def test_save_all_update_collision_flushed_by_next_merge_expect_integrity_error(
    engine: Engine,
) -> None:
    """save_all 도중 앞선 UPDATE가 다음 merge에서 flush되다 부딪히면 그대로 올린다."""
    _join(engine, "alice@example.com")
    bob = _join(engine, "bob@example.com")

    with Session(engine) as session, pytest.raises(IntegrityError):
        repository = _members(session)
        loaded = repository.get(bob.uid)
        loaded.email = "alice@example.com"
        repository.save_all([loaded, _member("erin@example.com")])


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_integrity_error("INSERT INTO t", sqlstate="23505"), True),
        (_integrity_error("  insert into t", pgcode="23505"), True),
        (
            _integrity_error(
                "INSERT INTO t", sqlite_errorname="SQLITE_CONSTRAINT_UNIQUE"
            ),
            True,
        ),
        (
            _integrity_error(
                "INSERT INTO t", sqlite_errorname="SQLITE_CONSTRAINT_PRIMARYKEY"
            ),
            True,
        ),
        (_integrity_error("INSERT INTO t", sqlstate="23503"), False),
        (
            _integrity_error(
                "INSERT INTO t", sqlite_errorname="SQLITE_CONSTRAINT_NOTNULL"
            ),
            False,
        ),
        (_integrity_error("UPDATE t SET", sqlstate="23505"), False),
        (_integrity_error(None, sqlstate="23505"), False),
        (_integrity_error("INSERT INTO t"), False),
    ],
)
def test_insert_unique_violation_detection_expect_only_insert_unique_codes(
    engine: Engine, error: IntegrityError, expected: bool
) -> None:
    """INSERT 문의 PostgreSQL 23505와 SQLite 유일·기본 키 코드만 유일 위반으로 본다."""
    with Session(engine) as session:
        assert _members(session)._is_insert_unique_violation(error) is expected
    assert _async_members(MagicMock())._is_insert_unique_violation(error) is expected


@pytest.mark.asyncio
async def test_async_save_new_aggregate_with_taken_unique_key_expect_already_exists() -> (
    None
):
    """비동기 save도 새 집합체 INSERT의 유일 위반을 EntityAlreadyExistsError로 바꾼다."""
    session = _async_session(merged_pending=True)
    session.flush.side_effect = _insert_unique_violation()
    member = _member("alice@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        await _async_members(session).save(member)

    assert error.value.args == (member.uid,)


@pytest.mark.asyncio
async def test_async_save_loaded_aggregate_unique_violation_expect_integrity_error() -> (
    None
):
    """비동기 save에서 기존 행을 고치다 난 무결성 오류는 그대로 올린다."""
    session = _async_session(merged_pending=False)
    session.flush.side_effect = _insert_unique_violation()

    with pytest.raises(IntegrityError):
        await _async_members(session).save(_member("alice@example.com"))


@pytest.mark.asyncio
async def test_async_save_all_new_duplicate_at_flush_expect_already_exists() -> None:
    """비동기 save_all의 마지막 flush에서 난 새 집합체 유일 위반을 알린다."""
    session = _async_session(merged_pending=True)
    session.flush.side_effect = _insert_unique_violation()
    member = _member("alice@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        await _async_members(session).save_all([member])

    assert error.value.args == ([member.uid],)


@pytest.mark.asyncio
async def test_async_save_all_new_duplicate_at_next_merge_expect_already_exists() -> (
    None
):
    """비동기 save_all 도중 다음 merge의 autoflush에서 난 새 집합체 유일 위반을 알린다."""
    session = _async_session(merged_pending=True)
    first_merged = session.merge.return_value
    session.merge.side_effect = [first_merged, _insert_unique_violation()]
    first = _member("alice@example.com")

    with pytest.raises(EntityAlreadyExistsError) as error:
        await _async_members(session).save_all([first, _member("bob@example.com")])

    assert error.value.args == ([first.uid],)


@pytest.mark.asyncio
async def test_async_save_all_without_new_aggregate_expect_integrity_error() -> None:
    """비동기 save_all에 새 집합체가 없으면 merge와 flush의 무결성 오류를 그대로 올린다."""
    merge_failing = _async_session(merged_pending=False)
    merge_failing.merge.side_effect = _insert_unique_violation()
    flush_failing = _async_session(merged_pending=False)
    flush_failing.flush.side_effect = _insert_unique_violation()

    for session in (merge_failing, flush_failing):
        with pytest.raises(IntegrityError):
            await _async_members(session).save_all([_member("alice@example.com")])
