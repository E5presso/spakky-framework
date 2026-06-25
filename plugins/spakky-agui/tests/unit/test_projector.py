"""Tests for the neutral AgentEvent -> AG-UI BaseEvent projector."""

from ag_ui.core import (
    CustomEvent,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder

from spakky.agent.event import (
    AgentEventAttribution,
    ArtifactEvent,
    MessageDeltaEvent,
    ReasoningDeltaEvent,
    RunFinishedEvent as NeutralRunFinishedEvent,
    RunStartedEvent as NeutralRunStartedEvent,
    StateDeltaEvent as NeutralStateDeltaEvent,
    StateSnapshotEvent as NeutralStateSnapshotEvent,
    StepFinishedEvent as NeutralStepFinishedEvent,
    StepStartedEvent as NeutralStepStartedEvent,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent as NeutralToolCallEndEvent,
    ToolCallResultEvent as NeutralToolCallResultEvent,
    ToolCallStartEvent as NeutralToolCallStartEvent,
)

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.projector import AgUiProjector


def _attribution(parent: str | None = None) -> AgentEventAttribution:
    return AgentEventAttribution(
        agent_id="assistant",
        run_id="run-1",
        conversation_id="conv-1",
        parent_run_id=parent,
    )


def _projector(
    *, emit_state_snapshot: bool = True, messages_snapshot: bool = False
) -> AgUiProjector:
    config = AgUiConfig()
    config.emit_state_snapshot = emit_state_snapshot
    config.messages_snapshot_enabled = messages_snapshot
    return AgUiProjector(config)


def test_message_delta_opens_message_then_content() -> None:
    """첫 MESSAGE_DELTA가 TEXT_MESSAGE_START + CONTENT를 연다."""
    projector = _projector()

    events = projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="hello")
    )

    assert isinstance(events[0], TextMessageStartEvent)
    assert events[0].message_id == "m1"
    assert events[0].role == "assistant"
    assert isinstance(events[1], TextMessageContentEvent)
    assert events[1].delta == "hello"


def test_message_delta_same_id_does_not_reopen() -> None:
    """동일 message_id의 연속 delta는 START를 다시 열지 않는다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )

    events = projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="b")
    )

    assert all(not isinstance(e, TextMessageStartEvent) for e in events)
    assert isinstance(events[0], TextMessageContentEvent)


def test_message_delta_new_id_closes_previous_message() -> None:
    """새 message_id는 이전 메시지를 END로 닫고 새 START를 연다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )

    events = projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m2", delta="b")
    )

    assert isinstance(events[0], TextMessageEndEvent)
    assert events[0].message_id == "m1"
    assert isinstance(events[1], TextMessageStartEvent)
    assert events[1].message_id == "m2"


def test_message_delta_empty_delta_skips_content() -> None:
    """빈 delta는 CONTENT를 생략한다(AG-UI가 빈 CONTENT를 거부)."""
    projector = _projector()

    events = projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="")
    )

    assert isinstance(events[0], TextMessageStartEvent)
    assert all(not isinstance(e, TextMessageContentEvent) for e in events)


def test_reasoning_delta_opens_full_reasoning_lifecycle() -> None:
    """REASONING_DELTA가 REASONING_START + MESSAGE_START + CONTENT를 연다."""
    projector = _projector()

    events = projector.project(
        ReasoningDeltaEvent(
            attribution=_attribution(), reasoning_id="r1", delta="think"
        )
    )

    assert isinstance(events[0], ReasoningStartEvent)
    assert isinstance(events[1], ReasoningMessageStartEvent)
    assert events[1].role == "reasoning"
    assert isinstance(events[2], ReasoningMessageContentEvent)
    assert events[2].delta == "think"


def test_reasoning_delta_empty_skips_content() -> None:
    """빈 reasoning delta는 CONTENT를 생략한다."""
    projector = _projector()

    events = projector.project(
        ReasoningDeltaEvent(attribution=_attribution(), reasoning_id="r1", delta="")
    )

    assert all(not isinstance(e, ReasoningMessageContentEvent) for e in events)


def test_reasoning_delta_same_id_does_not_reopen() -> None:
    """동일 reasoning_id의 연속 delta는 lifecycle을 다시 열지 않는다."""
    projector = _projector()
    projector.project(
        ReasoningDeltaEvent(attribution=_attribution(), reasoning_id="r1", delta="a")
    )

    events = projector.project(
        ReasoningDeltaEvent(attribution=_attribution(), reasoning_id="r1", delta="b")
    )

    assert all(not isinstance(e, ReasoningStartEvent) for e in events)


def test_finish_closes_open_message() -> None:
    """열린 메시지가 있으면 finish()가 END로 닫는다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )

    tail = projector.finish()

    assert isinstance(tail[0], TextMessageEndEvent)
    assert tail[0].message_id == "m1"


def test_finish_closes_open_reasoning() -> None:
    """열린 reasoning이 있으면 finish()가 MESSAGE_END + REASONING_END로 닫는다."""
    projector = _projector()
    projector.project(
        ReasoningDeltaEvent(attribution=_attribution(), reasoning_id="r1", delta="a")
    )

    tail = projector.finish()

    assert isinstance(tail[0], ReasoningMessageEndEvent)
    assert isinstance(tail[1], ReasoningEndEvent)


def test_finish_without_open_frames_is_empty() -> None:
    """열린 프레임이 없으면 finish()는 빈 목록을 반환한다."""
    projector = _projector()

    assert projector.finish() == []


def test_tool_start_uses_explicit_parent_message_id() -> None:
    """TOOL_CALL_START가 명시적 parent_message_id를 보존한다."""
    projector = _projector()

    events = projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(),
            call_id="c1",
            tool_name="lookup",
            parent_message_id="m9",
        )
    )

    assert isinstance(events[0], ToolCallStartEvent)
    assert events[0].tool_call_id == "c1"
    assert events[0].tool_call_name == "lookup"
    assert events[0].parent_message_id == "m9"


def test_tool_start_falls_back_to_open_message() -> None:
    """parent_message_id가 없으면 열린 메시지로 fallback한다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )

    events = projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(), call_id="c1", tool_name="lookup"
        )
    )

    assert isinstance(events[0], ToolCallStartEvent)
    assert events[0].parent_message_id == "m1"


def test_tool_args_empty_delta_is_dropped() -> None:
    """빈 args_delta는 TOOL_CALL_ARGS를 방출하지 않는다."""
    projector = _projector()

    events = projector.project(
        ToolCallArgsDeltaEvent(attribution=_attribution(), call_id="c1", args_delta="")
    )

    assert events == []


def test_tool_args_non_empty_delta_emits_args() -> None:
    """비어있지 않은 args_delta는 TOOL_CALL_ARGS를 방출한다."""
    projector = _projector()

    events = projector.project(
        ToolCallArgsDeltaEvent(
            attribution=_attribution(), call_id="c1", args_delta='{"x":1}'
        )
    )

    assert isinstance(events[0], ToolCallArgsEvent)
    assert events[0].delta == '{"x":1}'


def test_tool_end_emits_tool_call_end() -> None:
    """TOOL_CALL_END가 그대로 방출된다."""
    projector = _projector()

    events = projector.project(
        NeutralToolCallEndEvent(attribution=_attribution(), call_id="c1")
    )

    assert isinstance(events[0], ToolCallEndEvent)
    assert events[0].tool_call_id == "c1"


def test_finish_closes_open_tool_call_left_unended() -> None:
    """TOOL_CALL_END 없이 열린 도구 호출은 finish()가 TOOL_CALL_END로 닫는다."""
    projector = _projector()
    projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(), call_id="c1", tool_name="lookup"
        )
    )

    tail = projector.finish()

    assert [type(e).__name__ for e in tail] == ["ToolCallEndEvent"]
    assert isinstance(tail[0], ToolCallEndEvent)
    assert tail[0].tool_call_id == "c1"


def test_finish_closes_open_tool_calls_in_open_order_after_message() -> None:
    """열린 메시지와 도구 호출이 함께 있으면 메시지 END 후 도구 END를 open 순서로 닫는다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )
    projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(), call_id="c1", tool_name="first"
        )
    )
    projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(), call_id="c2", tool_name="second"
        )
    )

    tail = projector.finish()

    assert [type(e).__name__ for e in tail] == [
        "TextMessageEndEvent",
        "ToolCallEndEvent",
        "ToolCallEndEvent",
    ]
    assert [e.tool_call_id for e in tail if isinstance(e, ToolCallEndEvent)] == [
        "c1",
        "c2",
    ]


def test_ended_tool_call_is_not_reclosed_by_finish() -> None:
    """이미 TOOL_CALL_END로 닫힌 도구 호출은 finish()가 다시 닫지 않는다."""
    projector = _projector()
    projector.project(
        NeutralToolCallStartEvent(
            attribution=_attribution(), call_id="c1", tool_name="lookup"
        )
    )
    projector.project(NeutralToolCallEndEvent(attribution=_attribution(), call_id="c1"))

    assert projector.finish() == []


def test_tool_result_serializes_result_content() -> None:
    """TOOL_CALL_RESULT의 content가 result의 JSON 텍스트로 직렬화된다."""
    projector = _projector()

    events = projector.project(
        NeutralToolCallResultEvent(
            attribution=_attribution(),
            call_id="c1",
            tool_name="lookup",
            message_id="m2",
            result={"temp": 20},
        )
    )

    assert isinstance(events[0], ToolCallResultEvent)
    assert events[0].message_id == "m2"
    assert events[0].tool_call_id == "c1"
    assert events[0].content == '{"temp":20}'


def test_run_started_maps_attribution_to_thread_run_parent() -> None:
    """RUN_STARTED가 attribution을 threadId/runId/parentRunId로 매핑한다."""
    projector = _projector()

    events = projector.project(
        NeutralRunStartedEvent(attribution=_attribution(parent="parent-1"))
    )

    assert isinstance(events[0], RunStartedEvent)
    assert events[0].thread_id == "conv-1"
    assert events[0].run_id == "run-1"
    assert events[0].parent_run_id == "parent-1"
    encoded = EventEncoder().encode(events[0])
    assert '"threadId":"conv-1"' in encoded
    assert '"parentRunId":"parent-1"' in encoded


def test_run_finished_success_emits_run_finished_with_result() -> None:
    """error 없는 RUN_FINISHED가 result를 담은 RunFinishedEvent를 방출한다."""
    projector = _projector()

    events = projector.project(
        NeutralRunFinishedEvent(
            attribution=_attribution(), error=None, metadata={"output": {"a": 1}}
        )
    )

    finished = next(e for e in events if isinstance(e, RunFinishedEvent))
    assert finished.thread_id == "conv-1"
    assert finished.run_id == "run-1"
    assert finished.result == {"a": 1}


def test_run_finished_closes_open_message_before_terminal() -> None:
    """RUN_FINISHED는 종단 전에 열린 메시지를 닫는다."""
    projector = _projector()
    projector.project(
        MessageDeltaEvent(attribution=_attribution(), message_id="m1", delta="a")
    )

    events = projector.project(
        NeutralRunFinishedEvent(attribution=_attribution(), error=None, metadata={})
    )

    assert isinstance(events[0], TextMessageEndEvent)
    assert isinstance(events[-1], RunFinishedEvent)


def test_run_finished_with_error_emits_run_error() -> None:
    """error가 있는 RUN_FINISHED는 message/code를 담은 RUN_ERROR를 방출한다."""
    projector = _projector()

    events = projector.project(
        NeutralRunFinishedEvent(
            attribution=_attribution(),
            error={"code": "boom", "message": "failed"},
            metadata={},
        )
    )

    error = next(e for e in events if isinstance(e, RunErrorEvent))
    assert error.message == "failed"
    assert error.code == "boom"


def test_run_finished_error_reason_only_uses_reason_as_message() -> None:
    """message 없이 reason만 있는 error는 reason을 RUN_ERROR message로 쓴다."""
    projector = _projector()

    events = projector.project(
        NeutralRunFinishedEvent(
            attribution=_attribution(), error={"reason": "cancelled"}, metadata={}
        )
    )

    error = next(e for e in events if isinstance(e, RunErrorEvent))
    assert error.message == "cancelled"
    assert error.code is None


def test_run_finished_error_without_message_or_reason_serializes() -> None:
    """message/reason이 모두 없는 error는 JSON 직렬화 텍스트를 message로 쓴다."""
    projector = _projector()

    events = projector.project(
        NeutralRunFinishedEvent(
            attribution=_attribution(), error={"detail": "x"}, metadata={}
        )
    )

    error = next(e for e in events if isinstance(e, RunErrorEvent))
    assert error.message == '{"detail":"x"}'


def test_messages_snapshot_emitted_before_run_finished_when_enabled() -> None:
    """messages_snapshot_enabled면 RUN_FINISHED 직전에 MESSAGES_SNAPSHOT을 방출한다."""
    projector = _projector(messages_snapshot=True)

    events = projector.project(
        NeutralRunFinishedEvent(attribution=_attribution(), error=None, metadata={})
    )

    kinds = [type(e).__name__ for e in events]
    assert "MessagesSnapshotEvent" in kinds
    assert kinds.index("MessagesSnapshotEvent") < kinds.index("RunFinishedEvent")


def test_step_started_and_finished_map_by_name() -> None:
    """STEP_STARTED/FINISHED가 step_name을 보존하여 매핑된다."""
    projector = _projector()

    started = projector.project(
        NeutralStepStartedEvent(attribution=_attribution(), step_name="plan")
    )
    finished = projector.project(
        NeutralStepFinishedEvent(attribution=_attribution(), step_name="plan")
    )

    assert isinstance(started[0], StepStartedEvent)
    assert started[0].step_name == "plan"
    assert isinstance(finished[0], StepFinishedEvent)
    assert finished[0].step_name == "plan"


def test_state_snapshot_emitted_when_enabled() -> None:
    """emit_state_snapshot=True면 STATE_SNAPSHOT이 방출된다."""
    projector = _projector(emit_state_snapshot=True)

    events = projector.project(
        NeutralStateSnapshotEvent(attribution=_attribution(), snapshot={"count": 1})
    )

    assert isinstance(events[0], StateSnapshotEvent)
    assert events[0].snapshot == {"count": 1}


def test_state_snapshot_dropped_when_disabled() -> None:
    """emit_state_snapshot=False면 STATE_SNAPSHOT은 드롭된다."""
    projector = _projector(emit_state_snapshot=False)

    events = projector.project(
        NeutralStateSnapshotEvent(attribution=_attribution(), snapshot={"count": 1})
    )

    assert events == []


def test_state_delta_relays_patch_list() -> None:
    """STATE_DELTA가 JSON Patch 리스트를 그대로 전달한다."""
    projector = _projector()
    patch = [{"op": "add", "path": "/x", "value": 1}]

    events = projector.project(
        NeutralStateDeltaEvent(attribution=_attribution(), patch=patch)
    )

    assert isinstance(events[0], StateDeltaEvent)
    assert events[0].delta == patch


def test_state_delta_wraps_non_list_patch() -> None:
    """리스트가 아닌 patch는 단일 원소 리스트로 감싼다."""
    projector = _projector()

    events = projector.project(
        NeutralStateDeltaEvent(attribution=_attribution(), patch={"op": "replace"})
    )

    assert isinstance(events[0], StateDeltaEvent)
    assert events[0].delta == [{"op": "replace"}]


def test_artifact_maps_to_custom_event() -> None:
    """ARTIFACT가 name=artifact의 CUSTOM 이벤트로 매핑된다."""
    projector = _projector()

    events = projector.project(
        ArtifactEvent(
            attribution=_attribution(),
            artifact_id="a1",
            content={"k": "v"},
            name="result",
        )
    )

    assert isinstance(events[0], CustomEvent)
    assert events[0].name == "artifact"
    assert events[0].value == {
        "artifactId": "a1",
        "name": "result",
        "content": {"k": "v"},
    }
