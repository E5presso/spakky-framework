"""Human-in-the-loop approval workflow contracts."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.execution import AgentSignalKind
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.tooling import AgentToolDescriptor, ToolRisk
from spakky.agent.types import JsonObject, JsonValue
from spakky.agent.yield_ import AgentYield, AgentYieldKind, Approval

DEFAULT_APPROVAL_DECISIONS = tuple(ApprovalDecision)


class AgentApprovalBoundaryKind(StrEnum):
    """Action boundaries where orchestration may require human approval."""

    MODEL_CALL = "model_call"
    TOOL_INVOCATION = "tool_invocation"
    DELEGATION = "delegation"
    FINAL_PUBLICATION = "final_publication"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    CONTEXT_TRANSFORMATION = "context_transformation"
    CANCELLATION_RESUME = "cancellation_resume"


class AgentApprovalPlanAction(StrEnum):
    """Approval plan outcome before an action boundary is executed."""

    PROCEED = "proceed"
    WAIT_FOR_APPROVAL = "wait_for_approval"


@dataclass(frozen=True, slots=True)
class AgentApprovalRequest:
    """Approval request materialized at a risky action boundary."""

    id: str
    agent_state_id: str
    boundary: AgentApprovalBoundaryKind
    prompt: str
    risk: ToolRisk
    action_ref: str
    allowed_decisions: tuple[ApprovalDecision, ...] = DEFAULT_APPROVAL_DECISIONS
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject approval requests that cannot be matched by a signal."""
        _require_non_blank(self.id, "Agent approval id")
        _require_non_blank(self.agent_state_id, "Agent approval state id")
        _require_non_blank(self.prompt, "Agent approval prompt")
        _require_non_blank(self.action_ref, "Agent approval action ref")
        if len(self.allowed_decisions) == 0:
            raise AgentDefinitionError("Agent approval decisions cannot be empty")

    @classmethod
    def from_tool_descriptor(
        cls,
        *,
        approval_id: str,
        agent_state_id: str,
        descriptor: AgentToolDescriptor,
        prompt: str | None = None,
        call_id: str | None = None,
        metadata: JsonObject | None = None,
    ) -> "AgentApprovalRequest":
        """Build an approval request from a risky tool descriptor."""
        request_metadata = _tool_approval_metadata(descriptor, call_id, metadata or {})
        return cls(
            id=approval_id,
            agent_state_id=agent_state_id,
            boundary=AgentApprovalBoundaryKind.TOOL_INVOCATION,
            prompt=prompt or f"Approve tool invocation: {descriptor.name}",
            risk=descriptor.metadata.risk,
            action_ref=descriptor.identity.key,
            metadata=request_metadata,
        )

    def to_state(self, *, agent_type: str) -> AgentState:
        """Materialize the approval wait as interrupted lifecycle state."""
        _require_non_blank(agent_type, "Agent approval agent type")
        return AgentState(
            id=self.agent_state_id,
            agent_type=agent_type,
            status=AgentStatus.INTERRUPTED,
            transition=AgentStateTransition.WAITING_APPROVAL,
            reason=AgentStateReason.APPROVAL_REQUIRED,
            current_activity=self.prompt,
            metadata={"approval": self.to_metadata()},
        )

    def to_yield(self) -> AgentYield[Approval]:
        """Expose this approval request to an inbound adapter stream."""
        return AgentYield(
            kind=AgentYieldKind.APPROVAL,
            payload=Approval(
                id=self.id,
                prompt=self.prompt,
                allowed_decisions=self.allowed_decisions,
                metadata=self.to_metadata(),
            ),
        )

    def to_metadata(self) -> JsonObject:
        """Return JSON-compatible metadata for state, yield, and evidence."""
        return {
            "id": self.id,
            "agent_state_id": self.agent_state_id,
            "boundary": self.boundary.value,
            "action_ref": self.action_ref,
            "risk_axes": [axis.value for axis in self.risk.axes],
            "allowed_decisions": [
                decision.value for decision in self.allowed_decisions
            ],
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class AgentApprovalPlan:
    """Plan for an action boundary before executing it."""

    action: AgentApprovalPlanAction
    request: AgentApprovalRequest | None = None
    state: AgentState | None = None
    yield_item: AgentYield[Approval] | None = None

    @property
    def requires_approval(self) -> bool:
        """Return whether orchestration must wait for a HITL decision."""
        return self.action == AgentApprovalPlanAction.WAIT_FOR_APPROVAL


@dataclass(frozen=True, slots=True)
class AgentApprovalDecisionOutcome:
    """Typed result of an approval decision signal."""

    request_id: str
    decision: ApprovalDecision
    status: AgentStatus
    transition: AgentStateTransition
    reason: AgentStateReason | None = None
    modified_payload: JsonObject = field(default_factory=dict)
    comment: str | None = None


def plan_agent_tool_approval(
    *,
    descriptor: AgentToolDescriptor,
    approval_id: str,
    agent_state_id: str,
    agent_type: str,
    prompt: str | None = None,
    call_id: str | None = None,
    metadata: JsonObject | None = None,
) -> AgentApprovalPlan:
    """Plan whether a tool invocation should proceed or wait for approval."""
    if not descriptor.metadata.requires_approval_candidate:
        return AgentApprovalPlan(action=AgentApprovalPlanAction.PROCEED)

    request = AgentApprovalRequest.from_tool_descriptor(
        approval_id=approval_id,
        agent_state_id=agent_state_id,
        descriptor=descriptor,
        prompt=prompt,
        call_id=call_id,
        metadata=metadata,
    )
    return AgentApprovalPlan(
        action=AgentApprovalPlanAction.WAIT_FOR_APPROVAL,
        request=request,
        state=request.to_state(agent_type=agent_type),
        yield_item=request.to_yield(),
    )


def parse_agent_approval_decision_signal(
    signal: AgentSignal,
    *,
    request: AgentApprovalRequest | None = None,
) -> AgentApprovalDecisionOutcome:
    """Parse an approval decision signal into a typed workflow outcome."""
    if signal.kind != AgentSignalKind.APPROVAL_DECISION:
        raise AgentDefinitionError(
            "Agent approval signal kind must be approval_decision"
        )

    request_id = _require_payload_text(signal.payload, "request_id")
    if request is not None and request_id != request.id:
        raise AgentDefinitionError("Agent approval signal request id does not match")
    if request is not None and signal.agent_state_id != request.agent_state_id:
        raise AgentDefinitionError("Agent approval signal state id does not match")

    decision = _parse_approval_decision(
        _require_payload_text(signal.payload, "decision")
    )
    modified_payload = _payload_object(signal.payload.get("modified_payload", {}))
    comment = _optional_payload_text(signal.payload, "comment")
    status, transition, reason = _decision_state_target(decision)

    return AgentApprovalDecisionOutcome(
        request_id=request_id,
        decision=decision,
        status=status,
        transition=transition,
        reason=reason,
        modified_payload=modified_payload,
        comment=comment,
    )


def materialize_agent_approval_decision_state(
    current: AgentState,
    outcome: AgentApprovalDecisionOutcome,
) -> AgentState:
    """Apply a typed approval decision outcome to an existing state snapshot."""
    return AgentState(
        id=current.id,
        agent_type=current.agent_type,
        status=outcome.status,
        transition=outcome.transition,
        reason=outcome.reason,
        current_activity=_activity_for_decision(outcome),
        input_ref=current.input_ref,
        output_ref=current.output_ref,
        pending_signal_count=current.pending_signal_count,
        last_event_cursor=current.last_event_cursor,
        recovery_marker=current.recovery_marker,
        metadata={
            **current.metadata,
            "approval_decision": {
                "request_id": outcome.request_id,
                "decision": outcome.decision.value,
                "modified_payload": outcome.modified_payload,
                "comment": outcome.comment,
            },
        },
        created_at=current.created_at,
        updated_at=current.updated_at,
    )


def _tool_approval_metadata(
    descriptor: AgentToolDescriptor,
    call_id: str | None,
    metadata: JsonObject,
) -> JsonObject:
    result: dict[str, JsonValue] = {
        "tool_identity": descriptor.identity.key,
        "tool_schema_name": descriptor.schema.name,
        "tool_name": descriptor.name,
        "approval_requirement": descriptor.metadata.approval.value,
        "risk_axes": [axis.value for axis in descriptor.metadata.risk.axes],
        "metadata": metadata,
    }
    if call_id is not None:
        _require_non_blank(call_id, "Agent approval tool call id")
        result["call_id"] = call_id
    return result


def _decision_state_target(
    decision: ApprovalDecision,
) -> tuple[AgentStatus, AgentStateTransition, AgentStateReason | None]:
    if decision in (ApprovalDecision.APPROVE, ApprovalDecision.MODIFY):
        return AgentStatus.ACTIVE, AgentStateTransition.RUNNING, None
    if decision == ApprovalDecision.DEFER:
        return (
            AgentStatus.INTERRUPTED,
            AgentStateTransition.WAITING_APPROVAL,
            AgentStateReason.APPROVAL_DEFERRED,
        )
    if decision == ApprovalDecision.CANCEL:
        return (
            AgentStatus.CANCELLING,
            AgentStateTransition.CANCELLING,
            AgentStateReason.CANCELLATION_REQUESTED,
        )
    return (
        AgentStatus.FAILED,
        AgentStateTransition.FAILED,
        AgentStateReason.APPROVAL_REJECTED,
    )


def _activity_for_decision(outcome: AgentApprovalDecisionOutcome) -> str:
    if outcome.decision == ApprovalDecision.APPROVE:
        return "approval approved"
    if outcome.decision == ApprovalDecision.MODIFY:
        return "approval modified"
    if outcome.decision == ApprovalDecision.DEFER:
        return "approval deferred"
    if outcome.decision == ApprovalDecision.CANCEL:
        return "approval cancellation requested"
    return "approval rejected"


def _parse_approval_decision(value: str) -> ApprovalDecision:
    try:
        return ApprovalDecision(value)
    except ValueError as e:
        raise AgentDefinitionError("Agent approval decision is not supported") from e


def _payload_object(value: JsonValue) -> JsonObject:
    if isinstance(value, Mapping):
        return value
    raise AgentDefinitionError("Agent approval modified payload must be an object")


def _require_payload_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentDefinitionError(f"Agent approval signal {key} must be non-blank")
    return value


def _optional_payload_text(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgentDefinitionError(f"Agent approval signal {key} must be non-blank")
    return value


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")
