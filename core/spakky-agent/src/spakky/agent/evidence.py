"""Agent evidence contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.types import JsonObject


class AgentEvidenceKind(StrEnum):
    """Kinds of append-only evidence captured by agent execution."""

    MODEL = "model"
    TOOL = "tool"
    CONTEXT_MANIFEST = "context_manifest"
    CONTEXT_DIGEST = "context_digest"
    APPROVAL = "approval"
    DELEGATION = "delegation"
    OUTPUT_GUARD = "output_guard"


@dataclass(frozen=True, slots=True)
class AgentEvidence:
    """Append-only artifact captured during an agent execution."""

    id: str
    agent_state_id: str
    kind: AgentEvidenceKind
    payload: JsonObject = field(default_factory=dict)
    summary: str | None = None
    reference: str | None = None
    created_at: datetime | None = None
