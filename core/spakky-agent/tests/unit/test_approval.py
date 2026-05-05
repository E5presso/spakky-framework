"""Tests for risk-boundary HITL approval workflow contracts."""

from collections.abc import AsyncGenerator

import pytest

from spakky.agent import (
    Agent,
    AgentApprovalRequest,
    AgentApprovalBoundaryKind,
    AgentApprovalPlanAction,
    AgentDefinitionError,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    ApprovalDecision,
    EvidenceCapture,
    Final,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    ToolRiskAxis,
    agent_tool,
    materialize_agent_approval_decision_state,
    parse_agent_approval_decision_signal,
    plan_agent_tool_approval,
)


@Agent()
class ApprovalFixtureAgent:
    """Agent fixture with low and high risk tools."""

    @agent_tool(
        schema_name="workspace.read",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def read_file(self, path: str) -> str:
        return path

    @agent_tool(
        schema_name="shell.run",
        effects=ToolEffects.external_side_effect(),
        idempotency=Idempotency.NON_IDEMPOTENT,
        evidence=EvidenceCapture.SUMMARY,
        approval=ToolApprovalRequirement.DERIVED,
    )
    def run_shell(self, command: str) -> str:
        return command

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


def test_plan_agent_tool_approval_expect_risky_tool_yields_waiting_approval() -> None:
    """tool risk metadata가 approval-required state와 yield를 만든다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "shell.run"
    )

    plan = plan_agent_tool_approval(
        descriptor=descriptor,
        approval_id="approval-1",
        agent_state_id="run-1",
        agent_type="ApprovalFixtureAgent",
        call_id="tool-call-1",
    )

    assert plan.requires_approval is True
    assert plan.action == AgentApprovalPlanAction.WAIT_FOR_APPROVAL
    assert plan.request is not None
    assert plan.request.boundary == AgentApprovalBoundaryKind.TOOL_INVOCATION
    assert plan.state is not None
    assert plan.state.status == AgentStatus.INTERRUPTED
    assert plan.state.transition == AgentStateTransition.WAITING_APPROVAL
    assert plan.state.reason == AgentStateReason.APPROVAL_REQUIRED
    assert plan.yield_item is not None
    assert plan.yield_item.kind == AgentYieldKind.APPROVAL
    assert plan.yield_item.payload.allowed_decisions == tuple(ApprovalDecision)
    risk_axes = plan.yield_item.payload.metadata["risk_axes"]
    assert isinstance(risk_axes, list)
    risk_axis_values = {axis for axis in risk_axes if isinstance(axis, str)}
    assert risk_axis_values == {
        ToolRiskAxis.READ.value,
        ToolRiskAxis.WRITE.value,
        ToolRiskAxis.SIDE_EFFECT.value,
        ToolRiskAxis.NETWORK.value,
    }


def test_plan_agent_tool_approval_expect_low_risk_tool_proceeds_without_hitl() -> None:
    """low-risk 또는 approval-not-required tool은 승인 없이 진행한다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "workspace.read"
    )

    plan = plan_agent_tool_approval(
        descriptor=descriptor,
        approval_id="approval-1",
        agent_state_id="run-1",
        agent_type="ApprovalFixtureAgent",
    )

    assert plan.requires_approval is False
    assert plan.action == AgentApprovalPlanAction.PROCEED
    assert plan.request is None
    assert plan.state is None
    assert plan.yield_item is None


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_transition", "expected_reason"),
    [
        (
            ApprovalDecision.APPROVE,
            AgentStatus.ACTIVE,
            AgentStateTransition.RUNNING,
            None,
        ),
        (
            ApprovalDecision.MODIFY,
            AgentStatus.ACTIVE,
            AgentStateTransition.RUNNING,
            None,
        ),
        (
            ApprovalDecision.DEFER,
            AgentStatus.INTERRUPTED,
            AgentStateTransition.WAITING_APPROVAL,
            AgentStateReason.APPROVAL_DEFERRED,
        ),
        (
            ApprovalDecision.CANCEL,
            AgentStatus.CANCELLING,
            AgentStateTransition.CANCELLING,
            AgentStateReason.CANCELLATION_REQUESTED,
        ),
        (
            ApprovalDecision.REJECT,
            AgentStatus.FAILED,
            AgentStateTransition.FAILED,
            AgentStateReason.APPROVAL_REJECTED,
        ),
    ],
)
def test_parse_agent_approval_decision_signal_expect_typed_state_target(
    decision: ApprovalDecision,
    expected_status: AgentStatus,
    expected_transition: AgentStateTransition,
    expected_reason: AgentStateReason | None,
) -> None:
    """approve/reject/modify/defer/cancel decision이 typed signal로 처리된다."""
    signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={
            "request_id": "approval-1",
            "decision": decision.value,
            "modified_payload": {"command": "echo ok"},
            "comment": "operator reviewed",
        },
    )

    outcome = parse_agent_approval_decision_signal(signal)

    assert outcome.request_id == "approval-1"
    assert outcome.decision == decision
    assert outcome.status == expected_status
    assert outcome.transition == expected_transition
    assert outcome.reason == expected_reason
    assert outcome.modified_payload == {"command": "echo ok"}
    assert outcome.comment == "operator reviewed"


def test_materialize_agent_approval_decision_state_expect_separates_lifecycle() -> None:
    """waiting approval과 interrupted/cancelling/failed 상태를 구분한다."""
    waiting = AgentState(
        id="run-1",
        agent_type="ApprovalFixtureAgent",
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.WAITING_APPROVAL,
        reason=AgentStateReason.APPROVAL_REQUIRED,
    )
    reject_signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"request_id": "approval-1", "decision": "reject"},
    )

    outcome = parse_agent_approval_decision_signal(reject_signal)
    failed = materialize_agent_approval_decision_state(waiting, outcome)

    assert waiting.status == AgentStatus.INTERRUPTED
    assert waiting.transition == AgentStateTransition.WAITING_APPROVAL
    assert failed.status == AgentStatus.FAILED
    assert failed.transition == AgentStateTransition.FAILED
    assert failed.reason == AgentStateReason.APPROVAL_REJECTED
    assert failed.metadata["approval_decision"] == {
        "request_id": "approval-1",
        "decision": "reject",
        "modified_payload": {},
        "comment": None,
    }


def test_parse_agent_approval_decision_signal_expect_rejects_invalid_payload() -> None:
    """approval signal payload 오류가 custom error로 드러난다."""
    signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.USER_MESSAGE,
        payload={"request_id": "approval-1", "decision": "approve"},
    )

    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(signal)


def test_agent_approval_request_expect_rejects_unmatchable_request() -> None:
    """approval request는 signal과 매칭할 수 없는 식별자를 거부한다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "shell.run"
    )

    with pytest.raises(AgentDefinitionError):
        AgentApprovalRequest(
            id="approval-1",
            agent_state_id="run-1",
            boundary=AgentApprovalBoundaryKind.TOOL_INVOCATION,
            prompt="Approve?",
            risk=descriptor.metadata.risk,
            action_ref=descriptor.identity.key,
            allowed_decisions=(),
        )
    with pytest.raises(AgentDefinitionError):
        AgentApprovalRequest(
            id=" ",
            agent_state_id="run-1",
            boundary=AgentApprovalBoundaryKind.TOOL_INVOCATION,
            prompt="Approve?",
            risk=descriptor.metadata.risk,
            action_ref=descriptor.identity.key,
        )


def test_plan_agent_tool_approval_expect_preserves_prompt_and_optional_metadata() -> (
    None
):
    """approval request metadata는 call id 유무와 사용자 prompt를 보존한다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "shell.run"
    )

    plan_without_call_id = plan_agent_tool_approval(
        descriptor=descriptor,
        approval_id="approval-1",
        agent_state_id="run-1",
        agent_type="ApprovalFixtureAgent",
        prompt="Run deployment?",
        metadata={"source": "test"},
    )
    plan_with_call_id = plan_agent_tool_approval(
        descriptor=descriptor,
        approval_id="approval-2",
        agent_state_id="run-1",
        agent_type="ApprovalFixtureAgent",
        call_id="tool-call-1",
    )

    assert plan_without_call_id.request is not None
    assert plan_without_call_id.request.prompt == "Run deployment?"
    assert "call_id" not in plan_without_call_id.request.metadata
    assert plan_without_call_id.request.metadata["metadata"] == {"source": "test"}
    assert plan_with_call_id.request is not None
    assert plan_with_call_id.request.metadata["call_id"] == "tool-call-1"


def test_plan_agent_tool_approval_expect_rejects_invalid_state_metadata() -> None:
    """state/yield로 materialize할 수 없는 approval metadata는 custom error로 거부한다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "shell.run"
    )

    with pytest.raises(AgentDefinitionError):
        plan_agent_tool_approval(
            descriptor=descriptor,
            approval_id="approval-1",
            agent_state_id="run-1",
            agent_type=" ",
        )
    with pytest.raises(AgentDefinitionError):
        plan_agent_tool_approval(
            descriptor=descriptor,
            approval_id="approval-1",
            agent_state_id="run-1",
            agent_type="ApprovalFixtureAgent",
            call_id=" ",
        )


@pytest.mark.parametrize(
    ("decision", "expected_activity"),
    [
        (ApprovalDecision.APPROVE, "approval approved"),
        (ApprovalDecision.MODIFY, "approval modified"),
        (ApprovalDecision.DEFER, "approval deferred"),
        (ApprovalDecision.CANCEL, "approval cancellation requested"),
        (ApprovalDecision.REJECT, "approval rejected"),
    ],
)
def test_materialize_agent_approval_decision_state_expect_names_activity(
    decision: ApprovalDecision,
    expected_activity: str,
) -> None:
    """approval decision별 lifecycle activity가 typed하게 남는다."""
    waiting = AgentState(
        id="run-1",
        agent_type="ApprovalFixtureAgent",
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.WAITING_APPROVAL,
        reason=AgentStateReason.APPROVAL_REQUIRED,
    )
    signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"request_id": "approval-1", "decision": decision.value},
    )

    state = materialize_agent_approval_decision_state(
        waiting,
        parse_agent_approval_decision_signal(signal),
    )

    assert state.current_activity == expected_activity


def test_parse_agent_approval_decision_signal_expect_validates_request_payload() -> (
    None
):
    """approval decision signal은 request id, decision, metadata shape을 검증한다."""
    descriptor = Agent.get(ApprovalFixtureAgent).tool_catalog.by_schema_name(
        "shell.run"
    )
    request = AgentApprovalRequest.from_tool_descriptor(
        approval_id="approval-1",
        agent_state_id="run-1",
        descriptor=descriptor,
    )

    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={"request_id": "approval-2", "decision": "approve"},
            ),
            request=request,
        )
    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-2",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={"request_id": "approval-1", "decision": "approve"},
            ),
            request=request,
        )
    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={"request_id": "approval-1", "decision": "unknown"},
            )
        )
    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={
                    "request_id": "approval-1",
                    "decision": "approve",
                    "modified_payload": "bad",
                },
            )
        )
    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={
                    "request_id": "approval-1",
                    "decision": "approve",
                    "comment": " ",
                },
            )
        )
    with pytest.raises(AgentDefinitionError):
        parse_agent_approval_decision_signal(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={"request_id": " ", "decision": "approve"},
            )
        )
