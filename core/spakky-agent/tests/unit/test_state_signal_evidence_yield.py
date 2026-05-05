"""Tests for state, signal, evidence, and yield contracts."""

from collections.abc import AsyncGenerator

import pytest

from spakky.agent import (
    AgentDefinitionError,
    AgentEvidence,
    AgentEvidenceCandidate,
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
    Cancel,
    Evidence,
    Error,
    EvidenceCapture,
    Final,
    Message,
    Progress,
    Token,
    Tool,
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


def test_agent_evidence_candidate_expect_converts_tool_result() -> None:
    """tool result evidence 후보가 append-only AgentEvidence로 변환된다."""
    candidate = AgentEvidenceCandidate.tool_result(
        tool_identity="tests.WorkspaceTools:read_file",
        tool_schema_name="workspace.read_file",
        result={"content": "hello"},
        capture=EvidenceCapture.STRUCTURED,
        summary="read workspace file",
    )

    evidence = candidate.to_evidence(
        evidence_id="evidence-1",
        agent_state_id="run-1",
    )

    assert evidence.kind == AgentEvidenceKind.TOOL
    assert evidence.agent_state_id == "run-1"
    assert evidence.payload == {
        "tool_identity": "tests.WorkspaceTools:read_file",
        "tool_schema_name": "workspace.read_file",
        "capture": "structured",
        "result": {"content": "hello"},
    }
    assert evidence.summary == "read workspace file"


def test_agent_evidence_candidate_expect_rejects_blank_identity() -> None:
    """evidence 후보의 추적 식별자는 blank 문자열일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        AgentEvidenceCandidate.tool_result(
            tool_identity=" ",
            tool_schema_name="workspace.read_file",
            result={},
            capture=EvidenceCapture.STRUCTURED,
        )


def test_agent_evidence_candidate_expect_converts_decisions_to_evidence() -> None:
    """model/tool decision evidence 후보가 append-only artifact shape을 가진다."""
    model_candidate = AgentEvidenceCandidate.model_decision(
        model="vllm/qwen",
        decision={"next_action": "call_tool"},
    )
    tool_candidate = AgentEvidenceCandidate.tool_decision(
        tool_identity="tests.ShellTools:run",
        decision={"approved": False, "reason": "destructive"},
    )

    model_evidence = model_candidate.to_evidence(
        evidence_id="model-evidence-1",
        agent_state_id="run-1",
    )
    tool_evidence = tool_candidate.to_evidence(
        evidence_id="tool-evidence-1",
        agent_state_id="run-1",
    )

    assert model_evidence.kind == AgentEvidenceKind.MODEL
    assert model_evidence.payload == {
        "model": "vllm/qwen",
        "decision": {"next_action": "call_tool"},
    }
    assert tool_evidence.kind == AgentEvidenceKind.TOOL
    assert tool_evidence.payload == {
        "tool_identity": "tests.ShellTools:run",
        "decision": {"approved": False, "reason": "destructive"},
    }


def test_agent_yield_expect_supports_canonical_stream_vocabulary() -> None:
    """AgentYield가 ADR-0009의 canonical stream item vocabulary를 담는다."""
    progress = AgentYield(
        kind=AgentYieldKind.PROGRESS,
        payload=Progress(message="Inspecting", current_step="read"),
    )
    token = AgentYield(kind=AgentYieldKind.TOKEN, payload=Token("hel"))
    tool = AgentYield(
        kind=AgentYieldKind.TOOL,
        payload=Tool(name="read_file", call_id="call-1", result="content"),
    )
    final = AgentYield(
        kind=AgentYieldKind.FINAL, payload=Final(output="done", metadata={})
    )

    assert progress.payload.message == "Inspecting"
    assert progress.payload.current_step == "read"
    assert token.payload.text == "hel"
    assert tool.payload.name == "read_file"
    assert tool.payload.result == "content"
    assert final.payload.output == "done"


def test_agent_yield_kind_expect_covers_issue_215_status_vocabulary() -> None:
    """token/progress/tool/evidence/approval/final/error/cancel 상태를 열거한다."""
    yield_kinds = {kind.value for kind in AgentYieldKind}

    assert yield_kinds == {
        "token",
        "progress",
        "tool",
        "evidence",
        "approval",
        "final",
        "error",
        "cancel",
    }


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


def test_agent_yield_expect_supports_error_and_cancel_items() -> None:
    """error와 cancel stream item이 typed payload로 표현된다."""
    error_yield = AgentYield(
        kind=AgentYieldKind.ERROR,
        payload=Error(code="model_timeout", message="model timed out", retryable=True),
    )
    cancel_yield = AgentYield(
        kind=AgentYieldKind.CANCEL,
        payload=Cancel(reason="user requested", requested_by="signal-1"),
    )

    assert error_yield.payload.code == "model_timeout"
    assert error_yield.payload.retryable is True
    assert cancel_yield.payload.reason == "user requested"
    assert cancel_yield.payload.requested_by == "signal-1"


async def test_agent_yield_expect_inbound_adapter_collects_stream_directly() -> None:
    """inbound adapter collector가 별도 projector 없이 AgentYield stream을 소비한다."""

    async def execute() -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(kind=AgentYieldKind.TOKEN, payload=Token("hel"))
        yield AgentYield(kind=AgentYieldKind.PROGRESS, payload=Progress("reading"))
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output={"answer": "done"}, metadata={}),
        )

    events = [item async for item in execute()]

    assert [event.kind.value for event in events] == ["token", "progress", "final"]
    assert isinstance(events[0].payload, Token)
    assert isinstance(events[1].payload, Progress)
    assert isinstance(events[2].payload, Final)


def test_agent_yield_expect_keeps_legacy_payload_aliases() -> None:
    """기존 Message/TextDelta import는 progress/token payload alias로 남는다."""
    message = Message("Inspecting")
    delta = TextDelta("hel")

    assert isinstance(message, Progress)
    assert isinstance(delta, Token)
