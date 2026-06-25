"""Tests for the protocol-neutral agent event taxonomy.

The mapping tests model what the downstream AG-UI (group D) and A2A (group E)
adapters do: project each neutral event onto the target protocol and assert that
no attribution (agent / run / parent / conversation) is lost. The in-test
projection functions are deliberate stand-ins for those adapters — they encode
the AG-UI ``parentRunId``/``threadId`` and A2A ``contextId``/task-hierarchy
linkage the issue requires (SC-1), without importing any protocol library.
"""

from collections.abc import Mapping

import pytest
from spakky.agent import AgentDefinitionError
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    AgentEventKind,
    ArtifactEvent,
    MessageDeltaEvent,
    ReasoningDeltaEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.types import JsonValue


def _root_attribution() -> AgentEventAttribution:
    return AgentEventAttribution(
        agent_id="code-assistant",
        run_id="run-1",
        conversation_id="thread-1",
    )


def _delegated_attribution() -> AgentEventAttribution:
    return AgentEventAttribution(
        agent_id="researcher",
        run_id="run-2",
        conversation_id="thread-1",
        parent_run_id="run-1",
    )


def _every_event(attribution: AgentEventAttribution) -> tuple[AgentEvent, ...]:
    """One instance of every event kind sharing one attribution."""
    return (
        MessageDeltaEvent(attribution, message_id="msg-1", delta="Hel"),
        ReasoningDeltaEvent(attribution, reasoning_id="rsn-1", delta="thinking"),
        ToolCallStartEvent(
            attribution,
            call_id="call-1",
            tool_name="search",
            parent_message_id="msg-1",
        ),
        ToolCallArgsDeltaEvent(attribution, call_id="call-1", args_delta='{"q":'),
        ToolCallEndEvent(attribution, call_id="call-1"),
        ToolCallResultEvent(
            attribution,
            call_id="call-1",
            tool_name="search",
            message_id="msg-2",
            result={"hits": 3},
        ),
        RunStartedEvent(attribution),
        RunFinishedEvent(attribution),
        StepStartedEvent(attribution, step_name="model-call"),
        StepFinishedEvent(attribution, step_name="model-call"),
        StateSnapshotEvent(attribution, snapshot={"document": "draft"}),
        StateDeltaEvent(
            attribution,
            patch=[{"op": "replace", "path": "/document", "value": "final"}],
        ),
        ArtifactEvent(attribution, artifact_id="art-1", content={"url": "s3://x"}),
    )


def test_event_kinds_expect_one_member_per_taxonomy_kind() -> None:
    """taxonomy 종류 enum이 각 이벤트 종류와 1:1로 대응한다."""
    events = _every_event(_root_attribution())

    kinds = {event.kind for event in events}

    assert kinds == set(AgentEventKind)
    assert len(events) == len(AgentEventKind)


def test_every_event_expect_carries_full_attribution() -> None:
    """모든 이벤트가 agent/run/conversation attribution을 그대로 운반한다."""
    attribution = _root_attribution()

    for event in _every_event(attribution):
        assert event.attribution is attribution
        assert event.attribution.agent_id == "code-assistant"
        assert event.attribution.run_id == "run-1"
        assert event.attribution.conversation_id == "thread-1"


def test_root_run_attribution_expect_parent_run_id_is_none() -> None:
    """위임 트리 루트 실행은 parent run id가 없다."""
    attribution = _root_attribution()

    assert attribution.parent_run_id is None


def test_delegated_run_attribution_expect_links_to_parent_run() -> None:
    """위임된 실행은 부모 실행으로의 parent link를 운반한다."""
    attribution = _delegated_attribution()

    assert attribution.parent_run_id == "run-1"
    assert attribution.conversation_id == "thread-1"


@pytest.mark.parametrize(
    ("agent_id", "run_id", "conversation_id", "parent_run_id"),
    [
        (" ", "run-1", "thread-1", None),
        ("agent-1", "", "thread-1", None),
        ("agent-1", "run-1", "  ", None),
        ("agent-1", "run-1", "thread-1", "   "),
    ],
)
def test_attribution_expect_rejects_blank_identifiers(
    agent_id: str,
    run_id: str,
    conversation_id: str,
    parent_run_id: str | None,
) -> None:
    """식별 불가능한 attribution은 custom error로 거부된다."""
    with pytest.raises(AgentDefinitionError):
        AgentEventAttribution(
            agent_id=agent_id,
            run_id=run_id,
            conversation_id=conversation_id,
            parent_run_id=parent_run_id,
        )


def test_event_kind_expect_is_read_only_discriminant() -> None:
    """이벤트 kind는 생성자 인자가 아닌 고정 판별자다."""
    event = MessageDeltaEvent(_root_attribution(), message_id="msg-1", delta="x")

    assert event.kind is AgentEventKind.MESSAGE_DELTA
    with pytest.raises(AttributeError):
        event.kind = AgentEventKind.ARTIFACT  # type: ignore[misc] - frozen dataclass


# --- AG-UI lossless mapping (group D adapter projection) ---


def _to_ag_ui(event: AgentEvent) -> Mapping[str, JsonValue]:
    """Project a neutral event onto AG-UI BaseEvent shape (adapter stand-in)."""
    base: dict[str, JsonValue] = {
        "threadId": event.attribution.conversation_id,
        "runId": event.attribution.run_id,
        "parentRunId": event.attribution.parent_run_id,
    }
    match event:
        case MessageDeltaEvent(message_id=message_id, delta=delta):
            return {
                **base,
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": message_id,
                "delta": delta,
            }
        case ReasoningDeltaEvent(reasoning_id=reasoning_id, delta=delta):
            return {
                **base,
                "type": "THINKING_TEXT_MESSAGE_CONTENT",
                "reasoningId": reasoning_id,
                "delta": delta,
            }
        case ToolCallStartEvent(
            call_id=call_id,
            tool_name=tool_name,
            parent_message_id=parent_message_id,
        ):
            return {
                **base,
                "type": "TOOL_CALL_START",
                "toolCallId": call_id,
                "toolCallName": tool_name,
                "parentMessageId": parent_message_id,
            }
        case ToolCallArgsDeltaEvent(call_id=call_id, args_delta=args_delta):
            return {
                **base,
                "type": "TOOL_CALL_ARGS",
                "toolCallId": call_id,
                "delta": args_delta,
            }
        case ToolCallEndEvent(call_id=call_id):
            return {**base, "type": "TOOL_CALL_END", "toolCallId": call_id}
        case ToolCallResultEvent(
            call_id=call_id,
            message_id=message_id,
            result=result,
        ):
            return {
                **base,
                "type": "TOOL_CALL_RESULT",
                "toolCallId": call_id,
                "messageId": message_id,
                "content": result,
            }
        case RunStartedEvent():
            return {**base, "type": "RUN_STARTED"}
        case RunFinishedEvent(error=error):
            return {**base, "type": "RUN_ERROR" if error else "RUN_FINISHED"}
        case StepStartedEvent(step_name=step_name):
            return {**base, "type": "STEP_STARTED", "stepName": step_name}
        case StepFinishedEvent(step_name=step_name):
            return {**base, "type": "STEP_FINISHED", "stepName": step_name}
        case StateSnapshotEvent(snapshot=snapshot):
            return {**base, "type": "STATE_SNAPSHOT", "snapshot": snapshot}
        case StateDeltaEvent(patch=patch):
            return {**base, "type": "STATE_DELTA", "delta": patch}
        case ArtifactEvent(artifact_id=artifact_id, content=content):
            return {
                **base,
                "type": "CUSTOM",
                "name": "artifact",
                "value": {"artifactId": artifact_id, "content": content},
            }


def test_ag_ui_mapping_expect_preserves_attribution_for_every_event() -> None:
    """모든 중립 이벤트가 AG-UI threadId/runId/parentRunId로 무손실 매핑된다."""
    attribution = _delegated_attribution()

    for event in _every_event(attribution):
        projected = _to_ag_ui(event)

        assert projected["threadId"] == attribution.conversation_id
        assert projected["runId"] == attribution.run_id
        assert projected["parentRunId"] == attribution.parent_run_id
        assert projected["type"]


def test_ag_ui_mapping_expect_distinguishes_run_error_from_finish() -> None:
    """RunFinished의 error 유무가 AG-UI RUN_ERROR/RUN_FINISHED로 구분된다."""
    attribution = _root_attribution()

    finished = _to_ag_ui(RunFinishedEvent(attribution))
    errored = _to_ag_ui(RunFinishedEvent(attribution, error={"code": "boom"}))

    assert finished["type"] == "RUN_FINISHED"
    assert errored["type"] == "RUN_ERROR"


def test_ag_ui_mapping_expect_tool_call_lifecycle_shares_call_id() -> None:
    """도구 호출 4단계가 동일 toolCallId로 AG-UI에 연결된다."""
    attribution = _root_attribution()
    lifecycle = (
        ToolCallStartEvent(attribution, call_id="call-9", tool_name="search"),
        ToolCallArgsDeltaEvent(attribution, call_id="call-9", args_delta="{}"),
        ToolCallEndEvent(attribution, call_id="call-9"),
        ToolCallResultEvent(
            attribution,
            call_id="call-9",
            tool_name="search",
            message_id="msg-9",
        ),
    )

    projected_ids = {_to_ag_ui(event)["toolCallId"] for event in lifecycle}

    assert projected_ids == {"call-9"}


def test_ag_ui_mapping_expect_tool_result_preserves_message_id() -> None:
    """도구 결과의 message_id가 AG-UI 필수 messageId로 무손실 매핑된다."""
    event = ToolCallResultEvent(
        _root_attribution(),
        call_id="call-1",
        tool_name="search",
        message_id="msg-7",
        result={"hits": 1},
    )

    projected = _to_ag_ui(event)

    assert projected["type"] == "TOOL_CALL_RESULT"
    assert projected["messageId"] == "msg-7"
    assert projected["toolCallId"] == "call-1"


def test_ag_ui_mapping_expect_tool_call_start_projects_parent_message_id() -> None:
    """tool call의 parent_message_id가 AG-UI parentMessageId로 매핑된다."""
    linked = ToolCallStartEvent(
        _root_attribution(),
        call_id="call-1",
        tool_name="search",
        parent_message_id="msg-3",
    )
    unlinked = ToolCallStartEvent(
        _root_attribution(),
        call_id="call-2",
        tool_name="search",
    )

    assert _to_ag_ui(linked)["parentMessageId"] == "msg-3"
    assert _to_ag_ui(unlinked)["parentMessageId"] is None


# --- A2A lossless mapping (group E adapter projection) ---


def _to_a2a(event: AgentEvent) -> Mapping[str, JsonValue]:
    """Project neutral attribution onto A2A task linkage (adapter stand-in)."""
    return {
        "contextId": event.attribution.conversation_id,
        "taskId": event.attribution.run_id,
        "parentTaskId": event.attribution.parent_run_id,
        "agentId": event.attribution.agent_id,
        "kind": event.kind.value,
    }


def test_a2a_mapping_expect_run_maps_to_task_and_context() -> None:
    """중립 run/conversation이 A2A taskId/contextId로 무손실 매핑된다."""
    attribution = _delegated_attribution()

    for event in _every_event(attribution):
        projected = _to_a2a(event)

        assert projected["contextId"] == attribution.conversation_id
        assert projected["taskId"] == attribution.run_id
        assert projected["parentTaskId"] == attribution.parent_run_id
        assert projected["agentId"] == attribution.agent_id


def test_a2a_mapping_expect_root_task_has_no_parent() -> None:
    """루트 실행은 A2A에서 부모 task가 없는 최상위 task로 매핑된다."""
    projected = _to_a2a(RunStartedEvent(_root_attribution()))

    assert projected["parentTaskId"] is None
    assert projected["taskId"] == "run-1"


def test_cross_protocol_mapping_expect_same_neutral_event_round_trips_both() -> None:
    """동일 중립 이벤트가 AG-UI와 A2A 양쪽 attribution을 동시에 보존한다."""
    event = ToolCallResultEvent(
        _delegated_attribution(),
        call_id="call-1",
        tool_name="search",
        message_id="msg-1",
        result={"ok": True},
    )

    ag_ui = _to_ag_ui(event)
    a2a = _to_a2a(event)

    assert ag_ui["runId"] == a2a["taskId"] == "run-2"
    assert ag_ui["parentRunId"] == a2a["parentTaskId"] == "run-1"
    assert ag_ui["threadId"] == a2a["contextId"] == "thread-1"
