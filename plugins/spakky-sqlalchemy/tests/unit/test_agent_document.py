"""Unit tests for relational storage of agent JSON documents."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import cast

import pytest
from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStatus,
)
from spakky.agent.types import JsonValue
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.agent.document import (
    AgentJsonDocumentStore,
    AgentJsonNodeTable,
    JsonNode,
    JsonNodeKind,
    decode_document,
    encode_document,
)
from spakky.plugins.sqlalchemy.agent.error import AgentDocumentCorruptedError
from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceTable,
    AgentSignalTable,
    AgentStateTable,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@dataclass(slots=True)
class SessionManagerStub:
    """Minimal session manager shape used by repository unit tests."""

    session: Session


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """Create an isolated in-memory SQLAlchemy session."""
    engine = create_engine("sqlite:///:memory:")
    AgentStateTable.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


DOCUMENT: JsonValue = {
    "text": "값",
    "flag": True,
    "count": 3,
    "ratio": 0.5,
    "nothing": None,
    "a/b~c": [1, {"nested": []}, {}],
}


def test_encode_decode_round_trip_keeps_types_order_and_escaped_keys() -> None:
    """Every JSON type, key order, nesting and pointer escaping survive a round trip."""
    nodes = encode_document(DOCUMENT)
    assert {node.kind for node in nodes} == set(JsonNodeKind)
    assert any(node.path == "/a~1b~0c/1/nested" for node in nodes)
    restored = decode_document(reversed(nodes))
    assert restored == DOCUMENT
    assert list(cast(dict[str, JsonValue], restored)) == list(
        cast(dict[str, JsonValue], DOCUMENT)
    )
    assert decode_document(encode_document([])) == []
    assert decode_document(encode_document("scalar")) == "scalar"


def test_decode_rejects_rows_without_exactly_one_root() -> None:
    """Rows that are not one document are corrupted."""
    with pytest.raises(AgentDocumentCorruptedError):
        decode_document(())
    root = JsonNode("", None, None, 0, JsonNodeKind.NULL)
    with pytest.raises(AgentDocumentCorruptedError):
        decode_document((root, root))


def test_store_writes_only_changed_rows_and_deletes_documents(session: Session) -> None:
    """A rewrite updates changed values, adds new ones and removes dropped ones."""
    store = AgentJsonDocumentStore()
    store.write(session, "doc", {"history": [1, 2], "kind": "a"})
    session.flush()
    before = {
        row.path: row for row in session.scalars(select(AgentJsonNodeTable)).all()
    }
    store.write(session, "doc", {"history": [1, 2, 3], "kind": {"changed": True}})
    session.flush()
    assert store.read(session, "doc") == {
        "history": [1, 2, 3],
        "kind": {"changed": True},
    }
    assert before["/history/0"] in session.scalars(select(AgentJsonNodeTable)).all()
    store.write(session, "doc", {"history": []})
    session.flush()
    assert store.read(session, "doc") == {"history": []}
    assert store.read_many(session, ()) == {}
    assert store.read(session, "missing") is None
    store.delete(session, "doc")
    assert store.read(session, "doc") is None


def test_repositories_reject_non_object_documents(session: Session) -> None:
    """A metadata or payload document must be an object; a missing one is empty."""
    manager = cast(SessionManager, SessionManagerStub(session=session))
    states = SqlAlchemyAgentStateRepository(manager)
    bare = AgentState(id="bare", agent_type="A", status=AgentStatus.ACTIVE)
    session.add(AgentStateTable.from_domain(bare))
    session.flush()
    assert states.get("bare").metadata == {}
    row = session.get(AgentStateTable, "bare")
    assert row is not None and row.to_domain().metadata == {}
    states.save(AgentState(id="s", agent_type="A", status=AgentStatus.ACTIVE))
    AgentJsonDocumentStore().write(session, "state:s:metadata", [1])
    session.flush()
    with pytest.raises(AgentDocumentCorruptedError):
        states.get("s")


def test_evidence_counts_steps_and_origins(session: Session) -> None:
    """Evidence count, step lookup and origin lookup use their own queries."""
    manager = cast(SessionManager, SessionManagerStub(session=session))
    evidence = SqlAlchemyAgentEvidenceRepository(manager)
    assert evidence.count_by_state("run") == 0
    stored = evidence.append(
        AgentEvidence(
            id="run:evidence:1",
            agent_state_id="run",
            kind=AgentEvidenceKind.CONTEXT_MANIFEST,
            payload={"model_step": 1},
            digest="fingerprint",
            model_step=1,
            origin_refs=("source:a", "source:b", "source:a"),
        )
    )
    assert stored.origin_refs == ("source:a", "source:b")
    evidence.append(
        AgentEvidence(
            id="run:evidence:2",
            agent_state_id="run",
            kind=AgentEvidenceKind.TOOL,
            payload={"result": {"ok": True}},
        )
    )
    assert evidence.count_by_state("run") == 2
    assert evidence.has_step_evidence(
        "run", AgentEvidenceKind.CONTEXT_MANIFEST, 1, "fingerprint"
    )
    assert not evidence.has_step_evidence(
        "run", AgentEvidenceKind.CONTEXT_MANIFEST, 2, "fingerprint"
    )
    found = evidence.list_by_origin_ref("source:b")
    assert [item.id for item in found] == ["run:evidence:1"]
    assert found[0].payload == {"model_step": 1}
    assert found[0].origin_refs == ("source:a", "source:b")
    assert evidence.list_by_origin_ref("source:none") == []
    assert evidence.get("run:evidence:2").payload == {"result": {"ok": True}}
    rows = session.scalars(select(AgentEvidenceTable)).all()
    assert all(row.to_domain().payload == {} for row in rows)
    signals = SqlAlchemyAgentSignalRepository(manager)
    signals.append(
        AgentSignal(
            id="signal",
            agent_state_id="run",
            kind=AgentSignalKind.CANCEL,
            payload={"reason": "stop"},
        )
    )
    row = session.get(AgentSignalTable, "signal")
    assert row is not None and row.to_domain().payload == {}
    assert signals.list_pending("run")[0].payload == {"reason": "stop"}
