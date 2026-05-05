"""Tests for state, signal, evidence, and yield contracts."""

import pytest

from spakky.agent import (
    AgentDefinitionError,
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
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


def test_agent_evidence_expect_append_only_artifact_shape() -> None:
    """AgentEvidence가 update/delete 없이 append artifact shape만 제공한다."""
    evidence = AgentEvidence(
        id="evidence-1",
        agent_state_id="run-1",
        kind=AgentEvidenceKind.CONTEXT_DIGEST,
        payload={"digest": "abc"},
        summary="compressed context",
    )

    assert evidence.kind == AgentEvidenceKind.CONTEXT_DIGEST
    assert evidence.payload == {"digest": "abc"}
    assert evidence.summary == "compressed context"


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
