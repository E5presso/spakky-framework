"""Action-boundary recovery contracts for durable agent execution."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.evidence import (
    AgentEvidence,
    AgentEvidenceCandidate,
    AgentEvidenceKind,
)
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.signal import AgentSignal
from spakky.agent.tooling import Idempotency, ToolResumeAction, ToolResumeMetadata
from spakky.agent.types import JsonObject, JsonValue


class AgentActionKind(StrEnum):
    """Recoverable external action classes in an agent execution."""

    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    APPROVAL_WAIT = "approval_wait"


class AgentActionBoundaryStage(StrEnum):
    """Checkpoint side recorded around an action boundary."""

    BEFORE = "before"
    AFTER = "after"


class AgentResumeAction(StrEnum):
    """Orchestration action selected from persisted checkpoint evidence."""

    START = "start"
    SKIP_COMPLETED = "skip_completed"
    RETRY = "retry"
    REQUIRE_HITL = "require_hitl"
    NOT_RESUMABLE = "not_resumable"


@dataclass(frozen=True, slots=True)
class AgentActionBoundaryCheckpoint:
    """Serializable checkpoint recorded before or after one external action."""

    action_id: str
    action_kind: AgentActionKind
    stage: AgentActionBoundaryStage
    idempotency: Idempotency = Idempotency.UNKNOWN
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject checkpoints that cannot be correlated after restart."""
        if not self.action_id.strip():
            raise AgentDefinitionError("Agent action boundary id cannot be blank")

    @classmethod
    def before_model_call(
        cls,
        action_id: str,
        *,
        idempotency: Idempotency = Idempotency.UNKNOWN,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded before a model call is attempted."""
        return cls._for_action(
            action_id,
            AgentActionKind.MODEL_CALL,
            AgentActionBoundaryStage.BEFORE,
            idempotency=idempotency,
            metadata=metadata,
        )

    @classmethod
    def after_model_call(
        cls,
        action_id: str,
        *,
        idempotency: Idempotency = Idempotency.UNKNOWN,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded after a model call completes."""
        return cls._for_action(
            action_id,
            AgentActionKind.MODEL_CALL,
            AgentActionBoundaryStage.AFTER,
            idempotency=idempotency,
            metadata=metadata,
        )

    @classmethod
    def before_tool_call(
        cls,
        action_id: str,
        *,
        idempotency: Idempotency,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded before a tool call is attempted."""
        return cls._for_action(
            action_id,
            AgentActionKind.TOOL_CALL,
            AgentActionBoundaryStage.BEFORE,
            idempotency=idempotency,
            metadata=metadata,
        )

    @classmethod
    def after_tool_call(
        cls,
        action_id: str,
        *,
        idempotency: Idempotency,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded after a tool call completes."""
        return cls._for_action(
            action_id,
            AgentActionKind.TOOL_CALL,
            AgentActionBoundaryStage.AFTER,
            idempotency=idempotency,
            metadata=metadata,
        )

    @classmethod
    def before_approval_wait(
        cls,
        action_id: str,
        *,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded before waiting for approval."""
        return cls._for_action(
            action_id,
            AgentActionKind.APPROVAL_WAIT,
            AgentActionBoundaryStage.BEFORE,
            idempotency=Idempotency.NON_IDEMPOTENT,
            metadata=metadata,
        )

    @classmethod
    def after_approval_wait(
        cls,
        action_id: str,
        *,
        metadata: JsonObject | None = None,
    ) -> "AgentActionBoundaryCheckpoint":
        """Create the checkpoint recorded after an approval wait resolves."""
        return cls._for_action(
            action_id,
            AgentActionKind.APPROVAL_WAIT,
            AgentActionBoundaryStage.AFTER,
            idempotency=Idempotency.NON_IDEMPOTENT,
            metadata=metadata,
        )

    @classmethod
    def _for_action(
        cls,
        action_id: str,
        action_kind: AgentActionKind,
        stage: AgentActionBoundaryStage,
        *,
        idempotency: Idempotency,
        metadata: JsonObject | None,
    ) -> "AgentActionBoundaryCheckpoint":
        return cls(
            action_id=action_id,
            action_kind=action_kind,
            stage=stage,
            idempotency=idempotency,
            metadata={} if metadata is None else metadata,
        )

    def to_evidence_candidate(
        self,
        *,
        summary: str | None = None,
    ) -> AgentEvidenceCandidate:
        """Represent this checkpoint as append-only evidence."""
        return AgentEvidenceCandidate(
            kind=AgentEvidenceKind.ACTION_BOUNDARY,
            payload={
                "action_id": self.action_id,
                "action_kind": self.action_kind.value,
                "stage": self.stage.value,
                "idempotency": self.idempotency.value,
                "metadata": self.metadata,
            },
            summary=summary,
        )


@dataclass(frozen=True, slots=True)
class AgentResumeBoundary:
    """Last action boundary reconstructed from append-only evidence."""

    action_id: str
    action_kind: AgentActionKind
    stage: AgentActionBoundaryStage
    idempotency: Idempotency
    evidence_id: str


@dataclass(frozen=True, slots=True)
class AgentResumePlan:
    """Resume decision derived from persisted state and checkpoint evidence."""

    state: AgentState
    action: AgentResumeAction
    boundary: AgentResumeBoundary | None = None
    signals: tuple[AgentSignal, ...] = ()

    @property
    def requires_human_input(self) -> bool:
        """Return whether automatic replay must stop at HITL recovery."""
        return self.action is AgentResumeAction.REQUIRE_HITL

    @property
    def can_resume_automatically(self) -> bool:
        """Return whether orchestration may continue without approval."""
        return self.action in (
            AgentResumeAction.START,
            AgentResumeAction.SKIP_COMPLETED,
            AgentResumeAction.RETRY,
        )


def plan_agent_resume(
    state: AgentState,
    evidence: Sequence[AgentEvidence],
    signals: Sequence[AgentSignal] = (),
) -> AgentResumePlan:
    """Restore the next resume action using only persisted state and evidence."""
    persisted_signals = tuple(signals)
    if state.status in (
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.CANCELLED,
    ):
        return AgentResumePlan(
            state=state,
            action=AgentResumeAction.NOT_RESUMABLE,
            signals=persisted_signals,
        )

    boundary = _last_action_boundary(evidence)
    if boundary is None:
        return AgentResumePlan(
            state=state,
            action=AgentResumeAction.START,
            signals=persisted_signals,
        )

    if boundary.stage is AgentActionBoundaryStage.AFTER:
        return AgentResumePlan(
            state=replace(state, recovery_marker=boundary.action_id),
            action=AgentResumeAction.SKIP_COMPLETED,
            boundary=boundary,
            signals=persisted_signals,
        )

    if boundary.action_kind is AgentActionKind.APPROVAL_WAIT:
        return AgentResumePlan(
            state=_interrupt_for_human_recovery(state, boundary),
            action=AgentResumeAction.REQUIRE_HITL,
            boundary=boundary,
            signals=persisted_signals,
        )

    resume_action = ToolResumeMetadata(
        idempotency=boundary.idempotency,
    ).action_for_incomplete_boundary()
    if resume_action is ToolResumeAction.RETRY:
        return AgentResumePlan(
            state=replace(state, recovery_marker=boundary.action_id),
            action=AgentResumeAction.RETRY,
            boundary=boundary,
            signals=persisted_signals,
        )
    return AgentResumePlan(
        state=_interrupt_for_human_recovery(state, boundary),
        action=AgentResumeAction.REQUIRE_HITL,
        boundary=boundary,
        signals=persisted_signals,
    )


def _last_action_boundary(
    evidence: Sequence[AgentEvidence],
) -> AgentResumeBoundary | None:
    for artifact in reversed(evidence):
        if artifact.kind is not AgentEvidenceKind.ACTION_BOUNDARY:
            continue
        return _boundary_from_evidence(artifact)
    return None


def _boundary_from_evidence(evidence: AgentEvidence) -> AgentResumeBoundary:
    payload = evidence.payload
    return AgentResumeBoundary(
        action_id=_string_payload(payload, "action_id"),
        action_kind=_action_kind_payload(payload),
        stage=_boundary_stage_payload(payload),
        idempotency=_idempotency_payload(payload),
        evidence_id=evidence.id,
    )


def _string_payload(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentDefinitionError("Agent action boundary evidence is invalid")
    return value


def _action_kind_payload(payload: Mapping[str, JsonValue]) -> AgentActionKind:
    try:
        return AgentActionKind(_string_payload(payload, "action_kind"))
    except ValueError as e:
        raise AgentDefinitionError("Agent action boundary evidence is invalid") from e


def _boundary_stage_payload(
    payload: Mapping[str, JsonValue],
) -> AgentActionBoundaryStage:
    try:
        return AgentActionBoundaryStage(_string_payload(payload, "stage"))
    except ValueError as e:
        raise AgentDefinitionError("Agent action boundary evidence is invalid") from e


def _idempotency_payload(payload: Mapping[str, JsonValue]) -> Idempotency:
    try:
        return Idempotency(_string_payload(payload, "idempotency"))
    except ValueError as e:
        raise AgentDefinitionError("Agent action boundary evidence is invalid") from e


def _interrupt_for_human_recovery(
    state: AgentState,
    boundary: AgentResumeBoundary,
) -> AgentState:
    return replace(
        state,
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.INTERRUPTED,
        reason=AgentStateReason.RECOVERY_REQUIRES_HITL,
        recovery_marker=boundary.action_id,
    )
