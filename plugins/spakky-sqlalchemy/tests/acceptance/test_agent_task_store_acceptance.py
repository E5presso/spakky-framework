"""Acceptance tests for the SQLAlchemy conversation task store contribution."""

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from spakky.agent import ConversationTurn, ModelMessageRole
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.agent.error import AgentConversationAppendConflictError
from spakky.plugins.sqlalchemy.agent.repository import SqlAlchemyAgentTaskStore
from spakky.plugins.sqlalchemy.agent.table import AgentConversationTurnTable
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@dataclass(slots=True)
class _SessionManagerStub:
    session: Session


@pytest.fixture(name="engine")
def engine_fixture(tmp_path: Path) -> Generator[Engine, None, None]:
    """Create a file-backed SQLite database to model process restart."""
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-task-store.db'}")
    AgentConversationTurnTable.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _store(session: Session) -> SqlAlchemyAgentTaskStore:
    return SqlAlchemyAgentTaskStore(
        cast(SessionManager, _SessionManagerStub(session=session))
    )


def _turn(role: ModelMessageRole, content: str) -> ConversationTurn:
    return ConversationTurn(role=role, content=content)


def test_sqlalchemy_task_store_acceptance_expect_conversation_continues_after_restart(
    engine: Engine,
) -> None:
    """재시작 후에도 같은 conversation_id의 transcript가 순서대로 이어진다."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as first_session:
        _store(first_session).append_turns(
            "thread-1",
            [
                _turn(ModelMessageRole.USER, "My name is Ada."),
                _turn(ModelMessageRole.ASSISTANT, "Nice to meet you, Ada."),
            ],
        )
        first_session.commit()

    with session_factory() as restarted_session:
        store = _store(restarted_session)
        seeded = store.load_history("thread-1")
        store.append_turns(
            "thread-1",
            [
                _turn(ModelMessageRole.USER, "What is my name?"),
                _turn(ModelMessageRole.ASSISTANT, "Your name is Ada."),
            ],
        )
        restarted_session.commit()

    with session_factory() as reader:
        history = _store(reader).load_history("thread-1")

    assert [turn.content for turn in seeded] == [
        "My name is Ada.",
        "Nice to meet you, Ada.",
    ]
    assert [(turn.role, turn.content) for turn in history] == [
        (ModelMessageRole.USER, "My name is Ada."),
        (ModelMessageRole.ASSISTANT, "Nice to meet you, Ada."),
        (ModelMessageRole.USER, "What is my name?"),
        (ModelMessageRole.ASSISTANT, "Your name is Ada."),
    ]


def test_sqlalchemy_task_store_acceptance_expect_rolled_back_turns_not_stored(
    engine: Engine,
) -> None:
    """rollback된 트랜잭션의 turn은 transcript에 남지 않는다."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as failed_session:
        _store(failed_session).append_turns(
            "thread-1", [_turn(ModelMessageRole.USER, "lost")]
        )
        failed_session.rollback()

    with session_factory() as reader:
        assert _store(reader).load_history("thread-1") == []


def test_sqlalchemy_task_store_acceptance_expect_concurrent_appender_conflict(
    engine: Engine,
) -> None:
    """두 writer가 같은 대화에 동시에 append하면 한쪽만 저장되고 다른 쪽은 충돌 오류로 실패한다."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as seed_session:
        _store(seed_session).append_turns(
            "thread-1", [_turn(ModelMessageRole.USER, "question")]
        )
        seed_session.commit()

    def append_from_competitor(*_: object) -> None:
        with session_factory() as competitor_session:
            _store(competitor_session).append_turns(
                "thread-1", [_turn(ModelMessageRole.ASSISTANT, "competitor answer")]
            )
            competitor_session.commit()

    with session_factory() as late_session:
        # The competitor commits after this writer read the last position and
        # before its INSERT, which is the race between two concurrent runs.
        event.listen(late_session, "before_flush", append_from_competitor, once=True)
        with pytest.raises(AgentConversationAppendConflictError):
            _store(late_session).append_turns(
                "thread-1", [_turn(ModelMessageRole.ASSISTANT, "late answer")]
            )
        late_session.rollback()

    with session_factory() as reader:
        history = _store(reader).load_history("thread-1")
    assert [turn.content for turn in history] == ["question", "competitor answer"]
