"""Unit tests for the SQLAlchemy-backed conversation task store."""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from spakky.agent import ConversationTurn, ModelMessageRole
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.agent.error import AgentConversationAppendConflictError
from spakky.plugins.sqlalchemy.agent.repository import SqlAlchemyAgentTaskStore
from spakky.plugins.sqlalchemy.agent.table import AgentConversationTurnTable
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@dataclass(slots=True)
class SessionManagerStub:
    """Minimal session manager shape used by task store unit tests."""

    session: Session


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """Create an isolated in-memory SQLAlchemy session."""
    engine = create_engine("sqlite:///:memory:")
    AgentConversationTurnTable.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(name="store")
def store_fixture(session: Session) -> SqlAlchemyAgentTaskStore:
    """Return a task store bound to the isolated session."""
    return SqlAlchemyAgentTaskStore(
        cast(SessionManager, SessionManagerStub(session=session))
    )


def _user(content: str) -> ConversationTurn:
    return ConversationTurn(role=ModelMessageRole.USER, content=content)


def _assistant(content: str) -> ConversationTurn:
    return ConversationTurn(role=ModelMessageRole.ASSISTANT, content=content)


def test_task_store_load_history_of_unknown_conversation_expect_empty(
    store: SqlAlchemyAgentTaskStore,
) -> None:
    """저장된 turn이 없는 대화의 이력은 빈 sequence다."""
    assert store.load_history("never-seen") == []


def test_task_store_append_turns_expect_history_in_append_order(
    store: SqlAlchemyAgentTaskStore,
) -> None:
    """한 번에 append한 turn들이 넘긴 순서 그대로 조회된다."""
    turns = [_user("hello"), _assistant("hi"), _user("how are you?")]

    store.append_turns("conversation-1", turns)

    assert store.load_history("conversation-1") == turns


def test_task_store_append_turns_twice_expect_later_turns_after_earlier(
    store: SqlAlchemyAgentTaskStore, session: Session
) -> None:
    """이어서 append한 turn은 기존 마지막 position 뒤에 붙는다."""
    store.append_turns("conversation-1", [_user("first"), _assistant("second")])

    store.append_turns("conversation-1", [_user("third"), _assistant("fourth")])

    assert [turn.content for turn in store.load_history("conversation-1")] == [
        "first",
        "second",
        "third",
        "fourth",
    ]
    assert session.scalars(
        select(AgentConversationTurnTable.position)
        .where(AgentConversationTurnTable.conversation_id == "conversation-1")
        .order_by(AgentConversationTurnTable.position)
    ).all() == [0, 1, 2, 3]


def test_task_store_append_turns_to_two_conversations_expect_histories_separate(
    store: SqlAlchemyAgentTaskStore,
) -> None:
    """대화별 이력은 서로 섞이지 않고 각자 position 0부터 시작한다."""
    store.append_turns("conversation-a", [_user("a-1")])
    store.append_turns("conversation-b", [_user("b-1"), _assistant("b-2")])
    store.append_turns("conversation-a", [_assistant("a-2")])

    assert store.load_history("conversation-a") == [_user("a-1"), _assistant("a-2")]
    assert store.load_history("conversation-b") == [_user("b-1"), _assistant("b-2")]


def test_task_store_append_turn_with_metadata_expect_metadata_restored(
    store: SqlAlchemyAgentTaskStore, session: Session
) -> None:
    """turn metadata가 JSON으로 저장되고 그대로 복원된다."""
    turn = ConversationTurn(
        role=ModelMessageRole.ASSISTANT,
        content="done",
        metadata={"model": "fake", "usage": {"output_tokens": 3}},
    )

    store.append_turns("conversation-1", [turn])
    session.expire_all()

    assert store.load_history("conversation-1") == [turn]


def test_task_store_append_no_turns_expect_history_unchanged(
    store: SqlAlchemyAgentTaskStore,
) -> None:
    """빈 turn 목록을 append해도 이력이 바뀌지 않는다."""
    store.append_turns("conversation-1", [_user("only")])

    store.append_turns("conversation-1", [])

    assert store.load_history("conversation-1") == [_user("only")]


def test_task_store_append_at_taken_position_expect_conflict_error(
    store: SqlAlchemyAgentTaskStore, session: Session
) -> None:
    """다른 writer가 같은 position을 먼저 차지하면 순서를 바꾸지 않고 충돌 오류로 실패한다."""
    store.append_turns("conversation-1", [_user("first")])
    session.commit()
    session.add(
        AgentConversationTurnTable(
            id="competing-row",
            conversation_id="conversation-1",
            position=1,
            role=ModelMessageRole.ASSISTANT.value,
            content="competitor",
            metadata_json={},
            created_at=datetime(2026, 5, 6, tzinfo=UTC),
        )
    )

    with session.no_autoflush:
        with pytest.raises(AgentConversationAppendConflictError):
            store.append_turns("conversation-1", [_assistant("late")])
    session.rollback()

    assert store.load_history("conversation-1") == [_user("first")]
