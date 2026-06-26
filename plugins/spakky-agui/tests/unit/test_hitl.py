"""Tests for AG-UI human-in-the-loop projection and decision ingestion."""

from collections.abc import Sequence
from typing import override

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from pytest import mark, raises

from spakky.agent.event import (
    AgentEventAttribution,
    RunPausedEvent,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.execution import AgentSignalKind
from spakky.agent.interfaces.repository import IAgentSignalRepository
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.types import JsonObject, JsonValue
from spakky.agent.yield_ import Approval

from spakky.plugins.agui.error import AgUiApprovalDecodeError, AgUiPendingApprovalError
from spakky.plugins.agui.hitl import (
    approval_from_pause,
    carries_approval_decision,
    find_pending_approval,
    ingest_decision,
    project_approval,
    project_pending_approval,
)

_DEFAULT_APPROVAL: JsonObject = {
    "id": "approval:run-1:note.write",
    "allowed_decisions": ["approve", "reject"],
    "metadata": {"tool_name": "note_write"},
}
"""Well-formed approval metadata the runner stores on a WAIT_FOR_APPROVAL state."""

_APPROVAL_ID = "approval:run-1:note.write"
"""Core approval id namespace used by the runner for deferred approval calls."""


class _FakeSignalRepository(IAgentSignalRepository):
    def __init__(self) -> None:
        self.appended: list[AgentSignal] = []

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        self.appended.append(signal)
        return signal

    @override
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(s for s in self.appended if s.agent_state_id == state_id)

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        return next(s for s in self.appended if s.id == signal_id)


def _attribution() -> AgentEventAttribution:
    return AgentEventAttribution(
        agent_id="assistant", run_id="run-1", conversation_id="conv-1"
    )


def _tool_result_input(
    content: str,
    tool_call_id: str = _APPROVAL_ID,
) -> AgUiRunAgentInput:
    return AgUiRunAgentInput.model_validate(
        {
            "threadId": "conv-1",
            "runId": "run-1",
            "state": None,
            "messages": [
                {
                    "id": "msg-1",
                    "role": "tool",
                    "content": content,
                    "toolCallId": tool_call_id,
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": None,
        }
    )


def _forwarded_input(forwarded: object) -> AgUiRunAgentInput:
    return AgUiRunAgentInput.model_validate(
        {
            "threadId": "conv-1",
            "runId": "run-1",
            "state": None,
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": forwarded,
        }
    )


def test_project_approval_emits_deferred_tool_frame_without_result() -> None:
    """승인 요청이 결과 없는 hitl_approval deferred-tool 프레임으로 투영된다."""
    approval = Approval(
        id="appr-1",
        prompt="approve write?",
        allowed_decisions=(ApprovalDecision.APPROVE, ApprovalDecision.REJECT),
        metadata={"tool": "note.write"},
    )

    events = project_approval(approval, _attribution())

    assert isinstance(events[0], ToolCallStartEvent)
    assert events[0].call_id == "appr-1"
    assert events[0].tool_name == "hitl_approval"
    assert isinstance(events[1], ToolCallArgsDeltaEvent)
    assert '"prompt":"approve write?"' in events[1].args_delta
    assert '"allowed_decisions":["approve","reject"]' in events[1].args_delta
    assert '"tool":"note.write"' in events[1].args_delta
    assert isinstance(events[2], ToolCallEndEvent)
    assert not any(isinstance(e, ToolCallResultEvent) for e in events)


def test_approval_from_pause_preserves_prompt_decisions_and_metadata() -> None:
    """RunPausedEvent의 승인 envelope가 Approval로 손실 없이 변환된다."""
    pause = RunPausedEvent(
        attribution=_attribution(),
        reason=AgentStateReason.APPROVAL_REQUIRED,
        prompt="approve write?",
        state_id="run-1",
        approval_id="appr-1",
        tool_call_id="call-1",
        allowed_decisions=("approve", "reject"),
        metadata={"tool": "note.write"},
    )

    approval = approval_from_pause(pause)

    assert approval.id == "appr-1"
    assert approval.prompt == "approve write?"
    assert approval.allowed_decisions == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.REJECT,
    )
    assert approval.metadata == {"tool": "note.write"}


def test_approval_from_pause_without_approval_id_raises() -> None:
    """approval id 없는 pause event는 deferred approval로 투영할 수 없다."""
    pause = RunPausedEvent(
        attribution=_attribution(),
        reason=AgentStateReason.AUTH_REQUIRED,
        prompt="sign in",
        state_id="run-1",
    )

    with raises(AgUiPendingApprovalError):
        approval_from_pause(pause)


def test_ingest_decision_from_tool_result_writes_approval_signal() -> None:
    """tool-result 메시지의 결정이 APPROVAL_DECISION signal로 적재된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "approve"}}'
    )

    ingest_decision(ag_ui_input, signals, "run-1")

    assert len(signals.appended) == 1
    signal = signals.appended[0]
    assert signal.agent_state_id == "run-1"
    assert signal.kind is AgentSignalKind.APPROVAL_DECISION
    assert signal.payload == {"request_id": _APPROVAL_ID, "decision": "approve"}


def test_ingest_decision_carries_modified_payload_and_comment() -> None:
    """modified_payload/comment가 있으면 signal payload에 함께 적재된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "modify",'
        ' "modified_payload": {"topic": "x"}, "comment": "ok"}'
    )

    ingest_decision(ag_ui_input, signals, "run-1")

    payload = signals.appended[0].payload
    assert payload["modified_payload"] == {"topic": "x"}
    assert payload["comment"] == "ok"


def test_ingest_decision_from_forwarded_props_writes_signal() -> None:
    """forwardedProps.approvalDecision의 결정도 signal로 적재된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _forwarded_input(
        {"approvalDecision": {"request_id": "appr-1", "decision": "reject"}}
    )

    ingest_decision(ag_ui_input, signals, "run-1")

    assert signals.appended[0].payload["decision"] == "reject"


@mark.parametrize("decision", list(ApprovalDecision))
def test_ingest_decision_accepts_every_approval_decision(
    decision: ApprovalDecision,
) -> None:
    """모든 ApprovalDecision 멤버가 디코딩되어 signal로 적재된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "{decision.value}"}}'
    )

    ingest_decision(ag_ui_input, signals, "run-1")

    assert signals.appended[0].payload["decision"] == decision.value


def test_ingest_decision_without_any_decision_raises() -> None:
    """결정 페이로드가 전혀 없으면 AgUiApprovalDecodeError를 던진다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _forwarded_input(None)

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_with_missing_request_id_raises() -> None:
    """request_id가 빠진 결정은 AgUiApprovalDecodeError를 던진다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input('{"decision": "approve"}')

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_with_invalid_decision_raises() -> None:
    """ApprovalDecision에 없는 값은 AgUiApprovalDecodeError를 던진다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "explode"}}'
    )

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_with_non_string_decision_raises() -> None:
    """decision 값이 문자열이 아니면 AgUiApprovalDecodeError를 던진다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": 7}}'
    )

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_ignores_malformed_tool_content() -> None:
    """JSON이 아닌 tool content는 결정원으로 무시되어 디코드 에러로 떨어진다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input("not-json")

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_ignores_non_object_tool_content() -> None:
    """JSON 배열 등 object가 아닌 tool content는 결정원으로 무시된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input("[1, 2, 3]")

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_ignores_tool_content_without_decision_key() -> None:
    """decision 키가 없는 tool-result content는 결정원으로 무시된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input('{"result": "unrelated"}')

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")


def test_ingest_decision_ignores_unaddressed_tool_result_decision() -> None:
    """request_id와 toolCallId가 다른 일반 tool result는 approval resume이 아니다."""
    signals = _FakeSignalRepository()
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "approve"}}',
        tool_call_id="ordinary-tool-call",
    )

    with raises(AgUiApprovalDecodeError):
        ingest_decision(ag_ui_input, signals, "run-1")
    assert signals.appended == []


def test_carries_approval_decision_true_for_tool_result() -> None:
    """tool-result 결정이 있으면 carries_approval_decision이 True다."""
    ag_ui_input = _tool_result_input(
        f'{{"request_id": "{_APPROVAL_ID}", "decision": "approve"}}'
    )

    assert carries_approval_decision(ag_ui_input) is True


def test_carries_approval_decision_false_for_unaddressed_tool_result() -> None:
    """일반 tool result의 decision 필드는 resume 신호로 오인하지 않는다."""
    ag_ui_input = _tool_result_input(
        '{"request_id": "ordinary-tool-call", "decision": "approve"}',
        tool_call_id="ordinary-tool-call",
    )

    assert carries_approval_decision(ag_ui_input) is False


def test_carries_approval_decision_false_without_decision() -> None:
    """결정이 없으면 carries_approval_decision이 False다."""
    ag_ui_input = _forwarded_input({"unrelated": True})

    assert carries_approval_decision(ag_ui_input) is False


def _paused_state(
    *,
    status: AgentStatus = AgentStatus.INTERRUPTED,
    reason: AgentStateReason | None = AgentStateReason.APPROVAL_REQUIRED,
    current_activity: str | None = "Approve tool invocation: note_write",
    approval: JsonValue = _DEFAULT_APPROVAL,
    include_approval: bool = True,
) -> AgentState:
    metadata: JsonObject = {"approval": approval} if include_approval else {}
    return AgentState(
        id="run-1",
        agent_type="assistant",
        status=status,
        transition=AgentStateTransition.WAITING_APPROVAL,
        reason=reason,
        current_activity=current_activity,
        metadata=metadata,
    )


def test_find_pending_approval_rebuilds_approval_from_paused_state() -> None:
    """WAIT_FOR_APPROVAL 상태에서 approval 메타데이터로 Approval을 복원한다."""
    approval = find_pending_approval(_paused_state())

    assert approval is not None
    assert approval.id == "approval:run-1:note.write"
    assert approval.prompt == "Approve tool invocation: note_write"
    assert approval.allowed_decisions == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.REJECT,
    )
    assert approval.metadata == {"tool_name": "note_write"}


def test_find_pending_approval_returns_none_when_not_interrupted() -> None:
    """INTERRUPTED가 아니면 pending approval이 없다."""
    assert find_pending_approval(_paused_state(status=AgentStatus.COMPLETED)) is None


def test_find_pending_approval_returns_none_when_reason_not_approval() -> None:
    """reason이 approval_required가 아니면 pending approval이 없다."""
    assert find_pending_approval(_paused_state(reason=AgentStateReason.TIMEOUT)) is None


def test_find_pending_approval_without_metadata_raises() -> None:
    """approval 메타데이터가 없는 paused 상태는 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(_paused_state(include_approval=False))


def test_find_pending_approval_without_prompt_raises() -> None:
    """prompt(current_activity)가 없는 paused 상태는 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(_paused_state(current_activity=None))


def test_find_pending_approval_with_blank_id_raises() -> None:
    """approval id가 공백이면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={
                    "id": "   ",
                    "allowed_decisions": ["approve"],
                    "metadata": {},
                }
            )
        )


def test_find_pending_approval_with_non_string_id_raises() -> None:
    """approval id가 문자열이 아니면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={"id": 7, "allowed_decisions": ["approve"], "metadata": {}}
            )
        )


def test_find_pending_approval_with_non_list_decisions_raises() -> None:
    """allowed_decisions가 리스트가 아니면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={
                    "id": "appr-1",
                    "allowed_decisions": "approve",
                    "metadata": {},
                }
            )
        )


def test_find_pending_approval_with_non_string_decision_raises() -> None:
    """allowed_decisions 원소가 문자열이 아니면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={"id": "appr-1", "allowed_decisions": [7], "metadata": {}}
            )
        )


def test_find_pending_approval_with_unknown_decision_raises() -> None:
    """allowed_decisions에 모르는 값이 있으면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={
                    "id": "appr-1",
                    "allowed_decisions": ["explode"],
                    "metadata": {},
                }
            )
        )


def test_find_pending_approval_with_non_mapping_metadata_raises() -> None:
    """approval metadata가 매핑이 아니면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(
            _paused_state(
                approval={
                    "id": "appr-1",
                    "allowed_decisions": ["approve"],
                    "metadata": "x",
                }
            )
        )


def test_find_pending_approval_with_non_mapping_approval_raises() -> None:
    """approval 항목 자체가 매핑이 아니면 AgUiPendingApprovalError를 던진다."""
    with raises(AgUiPendingApprovalError):
        find_pending_approval(_paused_state(approval=["not", "a", "mapping"]))


def test_project_pending_approval_emits_deferred_tool_frame() -> None:
    """paused 상태가 deferred-tool 승인 프레임으로 투영된다."""
    events = project_pending_approval(_paused_state(), _attribution())

    assert isinstance(events[0], ToolCallStartEvent)
    assert events[0].tool_name == "hitl_approval"
    assert events[0].call_id == "approval:run-1:note.write"
    assert isinstance(events[-1], ToolCallEndEvent)
    assert not any(isinstance(event, ToolCallResultEvent) for event in events)


def test_project_pending_approval_returns_empty_when_not_paused() -> None:
    """paused가 아니면 빈 목록을 반환한다."""
    assert (
        project_pending_approval(
            _paused_state(status=AgentStatus.COMPLETED), _attribution()
        )
        == []
    )
