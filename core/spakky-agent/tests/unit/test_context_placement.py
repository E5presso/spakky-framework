"""Context placement, typed run extensions, and evidence query defaults."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast, override

import pytest

from spakky.agent import (
    AgentRunExtension,
    ContextPack,
    ContextPackRole,
    ContextPlacement,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    RunAgentInput,
)
from spakky.agent.content import TextPart
from spakky.agent.error import (
    AgentDefinitionError,
    AgentEvidenceOriginQueryUnsupportedError,
)
from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.interfaces.repository import IAgentEvidenceRepository


@dataclass(frozen=True, slots=True)
class Route(AgentRunExtension):
    """An application value carried by a run."""

    provider: str


@dataclass(frozen=True, slots=True)
class Owner(AgentRunExtension):
    """A second application value type."""

    owner_id: str


def pack(pack_id: str, placement: ContextPlacement) -> ContextPack:
    """Build a context pack with one placement."""
    return ContextPack(
        id=pack_id,
        content=pack_id,
        source="test",
        role=ContextPackRole.TASK,
        placement=placement,
    )


def test_assemble_places_system_prelude_and_trailer_packs() -> None:
    """System packs join the instructions; prelude precedes and trailer follows history."""
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "instructions"),
            ModelMessage.user("question"),
        ),
        context=(
            pack("trailer", ContextPlacement.TRAILER),
            pack("frame", ContextPlacement.PRELUDE),
            pack("persona", ContextPlacement.SYSTEM),
        ),
    )
    messages = request.assemble_messages()
    assert [message.role for message in messages] == [
        ModelMessageRole.SYSTEM,
        ModelMessageRole.EVIDENCE,
        ModelMessageRole.USER,
        ModelMessageRole.EVIDENCE,
    ]
    assert messages[0].content == "instructions\n\npersona"
    assert (messages[1].content, messages[3].content) == ("frame", "trailer")


def test_system_pack_without_text_instructions_becomes_its_own_system_message() -> None:
    """A system pack opens a system message when there is no text system message."""
    without = ModelRequest(
        messages=(ModelMessage.user("question"),),
        context=(pack("persona", ContextPlacement.SYSTEM),),
    )
    assert [m.content for m in without.assemble_messages()] == ["persona", "question"]
    multipart = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, (TextPart("instructions"),)),
            ModelMessage.user("question"),
        ),
        context=(pack("persona", ContextPlacement.SYSTEM),),
    )
    roles = [m.role for m in multipart.assemble_messages()]
    assert roles == [
        ModelMessageRole.SYSTEM,
        ModelMessageRole.SYSTEM,
        ModelMessageRole.USER,
    ]


def test_run_extensions_are_typed_and_unique() -> None:
    """A run carries typed extensions, one per type, and a request returns them by type."""
    route = Route("local")
    run = RunAgentInput(state_id="run", instruction="go", extensions=(route,))
    request = ModelRequest(messages=(), extensions=run.extensions)
    assert request.extension(Route) is route
    assert request.extension(Owner) is None
    assert request.snapshot().extension(Route) is route
    with pytest.raises(AgentDefinitionError, match="unique"):
        RunAgentInput(
            state_id="run", instruction="go", extensions=(route, Route("cloud"))
        )
    with pytest.raises(AgentDefinitionError, match="invalid"):
        ModelRequest(messages=(), extensions=(cast(AgentRunExtension, object()),))


class MemoryEvidence(IAgentEvidenceRepository):
    """Evidence store without an origin index."""

    def __init__(self, items: Sequence[AgentEvidence]) -> None:
        self._items = tuple(items)

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        return evidence

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        return next(item for item in self._items if item.id == evidence_id)

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(item for item in self._items if item.agent_state_id == state_id)

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        return ()


def test_default_evidence_queries_use_state_listing_and_reject_origin_lookup() -> None:
    """Counting and step lookup work from the listing; origin lookup needs an index."""
    store = MemoryEvidence(
        (
            AgentEvidence(
                id="e1",
                agent_state_id="run",
                kind=AgentEvidenceKind.CONTEXT,
                digest="d",
                model_step=1,
            ),
        )
    )
    assert store.count_by_state("run") == 1
    assert store.has_step_evidence("run", AgentEvidenceKind.CONTEXT, 1, "d")
    assert not store.has_step_evidence("run", AgentEvidenceKind.CONTEXT, 2, "d")
    with pytest.raises(AgentEvidenceOriginQueryUnsupportedError):
        store.list_by_origin_ref("source:1")
