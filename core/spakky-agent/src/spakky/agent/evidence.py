"""Agent evidence contracts."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.context import (
    ContextHealthSignal,
    ContextOptimizationAction,
    ContextOptimizationEvidenceStage,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.tooling import EvidenceCapture
from spakky.agent.types import JsonObject


class AgentEvidenceKind(StrEnum):
    """Kinds of append-only evidence captured by agent execution."""

    ACTION_BOUNDARY = "action_boundary"
    MODEL = "model"
    TOOL = "tool"
    CONTEXT = "context"
    CONTEXT_MANIFEST = "context_manifest"
    CONTEXT_DIGEST = "context_digest"
    CONTEXT_OPTIMIZATION = "context_optimization"
    EVALUATION = "evaluation"
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
    digest: str | None = None
    manifest_ref: str | None = None
    reference: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AgentEvidenceCandidate:
    """Append-only evidence candidate before repository id assignment."""

    kind: AgentEvidenceKind
    payload: JsonObject = field(default_factory=dict)
    summary: str | None = None
    digest: str | None = None
    manifest_ref: str | None = None
    reference: str | None = None

    @classmethod
    def tool_result(
        cls,
        *,
        tool_identity: str,
        tool_schema_name: str,
        result: JsonObject,
        capture: EvidenceCapture,
        summary: str | None = None,
    ) -> "AgentEvidenceCandidate":
        """Create evidence metadata for a captured tool result."""
        _require_non_blank(tool_identity, "Agent tool identity")
        _require_non_blank(tool_schema_name, "Agent tool schema name")
        return cls(
            kind=AgentEvidenceKind.TOOL,
            payload={
                "tool_identity": tool_identity,
                "tool_schema_name": tool_schema_name,
                "capture": capture.value,
                "result": result,
            },
            summary=summary,
        )

    @classmethod
    def model_decision(
        cls,
        *,
        model: str,
        decision: JsonObject,
        summary: str | None = None,
    ) -> "AgentEvidenceCandidate":
        """Create evidence metadata for a model decision."""
        _require_non_blank(model, "Agent model name")
        return cls(
            kind=AgentEvidenceKind.MODEL,
            payload={"model": model, "decision": decision},
            summary=summary,
        )

    @classmethod
    def tool_decision(
        cls,
        *,
        tool_identity: str,
        decision: JsonObject,
        summary: str | None = None,
    ) -> "AgentEvidenceCandidate":
        """Create evidence metadata for a tool-routing decision."""
        _require_non_blank(tool_identity, "Agent tool identity")
        return cls(
            kind=AgentEvidenceKind.TOOL,
            payload={"tool_identity": tool_identity, "decision": decision},
            summary=summary,
        )

    @classmethod
    def context_optimization(
        cls,
        *,
        action: ContextOptimizationAction,
        stage: ContextOptimizationEvidenceStage,
        signals: Sequence[ContextHealthSignal] = (),
        summary: str | None = None,
    ) -> "AgentEvidenceCandidate":
        """Create before/after evidence for a context optimization action."""
        _require_non_blank(action.id, "Context optimization action id")
        return cls(
            kind=AgentEvidenceKind.CONTEXT_OPTIMIZATION,
            payload={
                "stage": stage.value,
                "action": action.evidence_payload(),
                "signals": tuple(signal.evidence_payload() for signal in signals),
            },
            summary=summary,
            digest=action.digest_ref,
            manifest_ref=action.manifest_ref,
            reference=action.result_evidence_ref,
        )

    def to_evidence(
        self,
        *,
        evidence_id: str,
        agent_state_id: str,
        created_at: datetime | None = None,
    ) -> AgentEvidence:
        """Assign repository identity while preserving append-only contents."""
        _require_non_blank(evidence_id, "Agent evidence id")
        _require_non_blank(agent_state_id, "Agent state id")
        return AgentEvidence(
            id=evidence_id,
            agent_state_id=agent_state_id,
            kind=self.kind,
            payload=self.payload,
            summary=self.summary,
            digest=self.digest,
            manifest_ref=self.manifest_ref,
            reference=self.reference,
            created_at=created_at,
        )


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")
