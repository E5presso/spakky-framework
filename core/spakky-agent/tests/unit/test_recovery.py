"""Tests for action-boundary checkpoint and resume contracts."""

import pytest

from spakky.agent import (
    AgentActionBoundaryCheckpoint,
    AgentActionBoundaryStage,
    AgentActionKind,
    AgentDefinitionError,
    AgentEvidence,
    AgentEvidenceKind,
    AgentResumeAction,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    Idempotency,
    plan_agent_resume,
)


def test_action_boundary_checkpoint_expect_records_model_tool_approval_edges() -> None:
    """model/tool/approval action 전후 checkpoint가 evidence로 직렬화된다."""
    checkpoints = (
        AgentActionBoundaryCheckpoint.before_model_call("model-1"),
        AgentActionBoundaryCheckpoint.after_model_call("model-1"),
        AgentActionBoundaryCheckpoint.before_tool_call(
            "tool-1",
            idempotency=Idempotency.IDEMPOTENT,
        ),
        AgentActionBoundaryCheckpoint.after_tool_call(
            "tool-1",
            idempotency=Idempotency.IDEMPOTENT,
        ),
        AgentActionBoundaryCheckpoint.before_approval_wait("approval-1"),
        AgentActionBoundaryCheckpoint.after_approval_wait("approval-1"),
    )

    evidence = tuple(
        checkpoint.to_evidence_candidate().to_evidence(
            evidence_id=f"evidence-{index}",
            agent_state_id="run-1",
        )
        for index, checkpoint in enumerate(checkpoints, start=1)
    )

    assert {item.kind for item in evidence} == {AgentEvidenceKind.ACTION_BOUNDARY}
    assert [item.payload["action_kind"] for item in evidence] == [
        AgentActionKind.MODEL_CALL.value,
        AgentActionKind.MODEL_CALL.value,
        AgentActionKind.TOOL_CALL.value,
        AgentActionKind.TOOL_CALL.value,
        AgentActionKind.APPROVAL_WAIT.value,
        AgentActionKind.APPROVAL_WAIT.value,
    ]
    assert [item.payload["stage"] for item in evidence] == [
        AgentActionBoundaryStage.BEFORE.value,
        AgentActionBoundaryStage.AFTER.value,
        AgentActionBoundaryStage.BEFORE.value,
        AgentActionBoundaryStage.AFTER.value,
        AgentActionBoundaryStage.BEFORE.value,
        AgentActionBoundaryStage.AFTER.value,
    ]


def test_resume_plan_expect_skips_completed_action_boundary() -> None:
    """completed action은 idempotency와 무관하게 중복 실행하지 않는다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
    )
    evidence = (
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.before_tool_call(
                "tool-1",
                idempotency=Idempotency.IDEMPOTENT,
            ),
            evidence_id="boundary-1",
        ),
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.after_tool_call(
                "tool-1",
                idempotency=Idempotency.IDEMPOTENT,
            ),
            evidence_id="boundary-2",
        ),
    )

    plan = plan_agent_resume(state, evidence)

    assert plan.action == AgentResumeAction.SKIP_COMPLETED
    assert plan.boundary is not None
    assert plan.boundary.action_id == "tool-1"
    assert plan.state.recovery_marker == "tool-1"
    assert plan.can_resume_automatically is True


def test_resume_plan_expect_retries_incomplete_idempotent_action() -> None:
    """idempotent incomplete action은 restart 후 자동 retry 대상으로 복원된다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.INTERRUPTED,
    )
    evidence = (
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.before_model_call(
                "model-1",
                idempotency=Idempotency.IDEMPOTENT,
            ),
            evidence_id="boundary-1",
        ),
    )

    plan = plan_agent_resume(state, evidence)

    assert plan.action == AgentResumeAction.RETRY
    assert plan.boundary is not None
    assert plan.boundary.action_id == "model-1"
    assert plan.state.recovery_marker == "model-1"
    assert plan.requires_human_input is False


def test_resume_plan_expect_interrupts_uncertain_non_idempotent_action() -> None:
    """non-idempotent incomplete action은 state/evidence로 HITL 필요성을 드러낸다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
    )
    evidence = (
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.before_tool_call(
                "shell-1",
                idempotency=Idempotency.NON_IDEMPOTENT,
            ),
            evidence_id="boundary-1",
        ),
    )

    plan = plan_agent_resume(state, evidence)

    assert plan.action == AgentResumeAction.REQUIRE_HITL
    assert plan.state.status == AgentStatus.INTERRUPTED
    assert plan.state.transition == AgentStateTransition.INTERRUPTED
    assert plan.state.reason == AgentStateReason.RECOVERY_REQUIRES_HITL
    assert plan.state.recovery_marker == "shell-1"
    assert plan.requires_human_input is True


def test_resume_plan_expect_restores_point_from_persisted_state_signal_evidence() -> (
    None
):
    """restart 시 persisted state/signal/evidence만으로 approval boundary를 복원한다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
        pending_signal_count=1,
    )
    signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"decision": "approve"},
    )
    evidence = (
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.before_approval_wait("approval-1"),
            evidence_id="boundary-1",
        ),
    )

    plan = plan_agent_resume(state, evidence, signals=(signal,))

    assert plan.action == AgentResumeAction.REQUIRE_HITL
    assert plan.boundary is not None
    assert plan.boundary.action_kind == AgentActionKind.APPROVAL_WAIT
    assert plan.signals == (signal,)
    assert plan.state.recovery_marker == "approval-1"


def test_resume_plan_expect_terminal_state_is_not_resumable() -> None:
    """terminal state는 action boundary evidence가 있어도 resume 후보가 아니다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.COMPLETED,
    )
    evidence = (
        _checkpoint_evidence(
            AgentActionBoundaryCheckpoint.before_tool_call(
                "tool-1",
                idempotency=Idempotency.IDEMPOTENT,
            ),
            evidence_id="boundary-1",
        ),
    )

    plan = plan_agent_resume(state, evidence)

    assert plan.action == AgentResumeAction.NOT_RESUMABLE
    assert plan.boundary is None


def test_resume_plan_expect_distinguishes_terminal_and_interrupted_causes() -> None:
    """timed_out/failed/cancelled는 terminal이고 interrupted는 recovery 후보로 남는다."""
    timed_out = AgentState(
        id="run-timeout",
        agent_type="CodeAssistant",
        status=AgentStatus.FAILED,
        transition=AgentStateTransition.TIMED_OUT,
        reason=AgentStateReason.TIMEOUT,
    )
    failed = AgentState(
        id="run-failed",
        agent_type="CodeAssistant",
        status=AgentStatus.FAILED,
        transition=AgentStateTransition.FAILED,
        reason=AgentStateReason.EXECUTION_FAILED,
    )
    interrupted = AgentState(
        id="run-interrupted",
        agent_type="CodeAssistant",
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.INTERRUPTED,
        reason=AgentStateReason.USER_INTERRUPTED,
    )
    cancelled = AgentState(
        id="run-cancelled",
        agent_type="CodeAssistant",
        status=AgentStatus.CANCELLED,
        transition=AgentStateTransition.CANCELLED,
        reason=AgentStateReason.CANCELLATION_REQUESTED,
    )

    timeout_plan = plan_agent_resume(timed_out, ())
    failed_plan = plan_agent_resume(failed, ())
    interrupted_plan = plan_agent_resume(interrupted, ())
    cancelled_plan = plan_agent_resume(cancelled, ())

    assert timeout_plan.action == AgentResumeAction.NOT_RESUMABLE
    assert failed_plan.action == AgentResumeAction.NOT_RESUMABLE
    assert interrupted_plan.action == AgentResumeAction.START
    assert cancelled_plan.action == AgentResumeAction.NOT_RESUMABLE
    assert timed_out.reason == AgentStateReason.TIMEOUT
    assert failed.reason == AgentStateReason.EXECUTION_FAILED
    assert interrupted.reason == AgentStateReason.USER_INTERRUPTED
    assert cancelled.reason == AgentStateReason.CANCELLATION_REQUESTED


def test_resume_plan_expect_starts_when_no_action_boundary_exists() -> None:
    """action boundary evidence가 아직 없으면 처음 safe point부터 시작한다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
    )
    evidence = (
        AgentEvidence(
            id="model-1",
            agent_state_id="run-1",
            kind=AgentEvidenceKind.MODEL,
            payload={"decision": "inspect"},
        ),
    )

    plan = plan_agent_resume(state, evidence)

    assert plan.action == AgentResumeAction.START
    assert plan.boundary is None
    assert plan.can_resume_automatically is True


def test_action_boundary_checkpoint_expect_rejects_blank_action_id() -> None:
    """action id가 blank면 restart 후 correlation할 수 없어 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentActionBoundaryCheckpoint.before_model_call(" ")


def test_resume_plan_expect_rejects_corrupt_boundary_evidence() -> None:
    """boundary evidence가 action id를 잃으면 custom error로 실패한다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
    )
    evidence = (
        AgentEvidence(
            id="boundary-1",
            agent_state_id="run-1",
            kind=AgentEvidenceKind.ACTION_BOUNDARY,
            payload={"action_id": " "},
        ),
    )

    with pytest.raises(AgentDefinitionError):
        plan_agent_resume(state, evidence)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "action_id": "action-1",
            "action_kind": "missing_kind",
            "stage": AgentActionBoundaryStage.BEFORE.value,
            "idempotency": Idempotency.IDEMPOTENT.value,
        },
        {
            "action_id": "action-1",
            "action_kind": AgentActionKind.TOOL_CALL.value,
            "stage": "missing_stage",
            "idempotency": Idempotency.IDEMPOTENT.value,
        },
        {
            "action_id": "action-1",
            "action_kind": AgentActionKind.TOOL_CALL.value,
            "stage": AgentActionBoundaryStage.BEFORE.value,
            "idempotency": "missing_idempotency",
        },
    ],
)
def test_resume_plan_expect_rejects_corrupt_boundary_enum_values(
    payload: dict[str, str],
) -> None:
    """boundary enum payload가 손상되면 ValueError 대신 custom error를 낸다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
    )
    evidence = (
        AgentEvidence(
            id="boundary-1",
            agent_state_id="run-1",
            kind=AgentEvidenceKind.ACTION_BOUNDARY,
            payload=payload,
        ),
    )

    with pytest.raises(AgentDefinitionError):
        plan_agent_resume(state, evidence)


def _checkpoint_evidence(
    checkpoint: AgentActionBoundaryCheckpoint,
    *,
    evidence_id: str,
) -> AgentEvidence:
    return checkpoint.to_evidence_candidate().to_evidence(
        evidence_id=evidence_id,
        agent_state_id="run-1",
    )
