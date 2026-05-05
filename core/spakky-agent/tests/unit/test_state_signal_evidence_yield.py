"""Tests for state, signal, evidence, and yield contracts."""

import pytest

from spakky.agent import (
    AgentDefinitionError,
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Approval,
    ApprovalDecision,
    Checkpoint,
    Evidence,
    Final,
    Message,
    TextDelta,
)


def test_agent_state_expect_uses_adr_lifecycle_statuses() -> None:
    """AgentState가 WAITING_APPROVAL 없이 INTERRUPTED lifecycle을 사용한다."""
    state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.INTERRUPTED,
        current_activity="approval required",
        pending_signal_count=2,
    )

    assert state.status == AgentStatus.INTERRUPTED
    assert state.pending_signal_count == 2
    assert state.current_activity == "approval required"


def test_agent_state_expect_expresses_issue_transition_vocabulary() -> None:
    """이슈 #221의 전이 어휘를 ADR top-level status와 분리해 표현한다."""
    approval_state = AgentState(
        id="run-1",
        agent_type="CodeAssistant",
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.WAITING_APPROVAL,
        reason=AgentStateReason.APPROVAL_REQUIRED,
    )
    timeout_state = AgentState(
        id="run-2",
        agent_type="CodeAssistant",
        status=AgentStatus.FAILED,
        transition=AgentStateTransition.TIMED_OUT,
        reason=AgentStateReason.TIMEOUT,
    )

    assert approval_state.status == AgentStatus.INTERRUPTED
    assert approval_state.transition == AgentStateTransition.WAITING_APPROVAL
    assert approval_state.reason == AgentStateReason.APPROVAL_REQUIRED
    assert timeout_state.status == AgentStatus.FAILED
    assert timeout_state.transition == AgentStateTransition.TIMED_OUT
    assert timeout_state.reason == AgentStateReason.TIMEOUT


def test_agent_state_transition_expect_covers_durable_execution_flow() -> None:
    """pending부터 terminal state까지 durable execution 전이를 열거한다."""
    transitions = {transition.value for transition in AgentStateTransition}

    assert transitions == {
        "pending",
        "running",
        "waiting_approval",
        "cancelling",
        "cancelled",
        "completed",
        "failed",
        "timed_out",
        "interrupted",
    }


def test_agent_state_expect_rejects_negative_pending_signal_count() -> None:
    """state snapshot이 불가능한 signal count를 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentState(
            id="run-1",
            agent_type="CodeAssistant",
            status=AgentStatus.ACTIVE,
            pending_signal_count=-1,
        )


def test_agent_signal_expect_carries_inbound_stimulus_payload() -> None:
    """AgentSignal이 실행 중 외부 입력을 durable queue item처럼 표현한다."""
    signal = AgentSignal(
        id="signal-1",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"decision": ApprovalDecision.APPROVE.value},
    )

    assert signal.kind == AgentSignalKind.APPROVAL_DECISION
    assert signal.payload == {"decision": "approve"}


def test_agent_signal_expect_covers_durable_inbound_queue_vocabulary() -> None:
    """user message, approval decision, cancel, resume 신호를 표현한다."""
    signal_kinds = {kind.value for kind in AgentSignalKind}

    assert {
        "user_message",
        "approval_decision",
        "cancel",
        "resume",
    } <= signal_kinds


def test_agent_evidence_expect_append_only_artifact_shape() -> None:
    """AgentEvidence가 update/delete 없이 append artifact shape만 제공한다."""
    evidence = AgentEvidence(
        id="evidence-1",
        agent_state_id="run-1",
        kind=AgentEvidenceKind.CONTEXT_DIGEST,
        payload={"digest": "abc"},
        summary="compressed context",
        digest="sha256:abc",
        manifest_ref="manifest-1",
    )

    assert evidence.kind == AgentEvidenceKind.CONTEXT_DIGEST
    assert evidence.payload == {"digest": "abc"}
    assert evidence.summary == "compressed context"
    assert evidence.digest == "sha256:abc"
    assert evidence.manifest_ref == "manifest-1"


def test_agent_evidence_kind_expect_covers_required_evidence_sources() -> None:
    """tool/model/context/evaluation evidence와 digest/manifest를 표현한다."""
    evidence_kinds = {kind.value for kind in AgentEvidenceKind}

    assert {
        "tool",
        "model",
        "context",
        "context_digest",
        "context_manifest",
        "evaluation",
    } <= evidence_kinds


def test_agent_yield_expect_supports_canonical_stream_vocabulary() -> None:
    """AgentYield가 ADR-0009의 canonical stream item vocabulary를 담는다."""
    message = AgentYield(kind=AgentYieldKind.MESSAGE, payload=Message("Inspecting"))
    delta = AgentYield(kind=AgentYieldKind.TEXT_DELTA, payload=TextDelta("hel"))
    checkpoint = AgentYield(
        kind=AgentYieldKind.CHECKPOINT,
        payload=Checkpoint(marker="action-1", metadata={}),
    )
    final = AgentYield(
        kind=AgentYieldKind.FINAL, payload=Final(output="done", metadata={})
    )

    assert message.payload.text == "Inspecting"
    assert delta.payload.text == "hel"
    assert checkpoint.payload.marker == "action-1"
    assert final.payload.output == "done"


def test_agent_yield_expect_supports_evidence_and_approval_items() -> None:
    """evidence와 approval stream item이 typed payload로 표현된다."""
    evidence = AgentEvidence(
        id="evidence-1",
        agent_state_id="run-1",
        kind=AgentEvidenceKind.TOOL,
    )
    evidence_yield = AgentYield(
        kind=AgentYieldKind.EVIDENCE, payload=Evidence(evidence)
    )
    approval_yield = AgentYield(
        kind=AgentYieldKind.APPROVAL,
        payload=Approval(
            id="approval-1",
            prompt="Run shell command?",
            allowed_decisions=(ApprovalDecision.APPROVE, ApprovalDecision.CANCEL),
            metadata={},
        ),
    )

    assert evidence_yield.payload.evidence is evidence
    assert approval_yield.payload.allowed_decisions == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.CANCEL,
    )
