"""Tests for the AG-UI SSE run driver consuming the neutral event stream."""

from collections.abc import AsyncGenerator
from json import loads
from typing import cast

from ag_ui.encoder import EventEncoder

from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    MessageDeltaEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.inbound import RunAgentInput
from spakky.agent.runner import AgentRunner
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver

_ATTRIBUTION = AgentEventAttribution(
    agent_id="assistant", run_id="run-1", conversation_id="conv-1"
)


class _ScriptedRunner:
    """Fake runner replaying a fixed neutral AgentEvent script over run_events."""

    def __init__(
        self,
        script: tuple[AgentEvent, ...],
        states: object | None = None,
    ) -> None:
        self._script = script
        self.states = states

    async def run_events(
        self, run_input: RunAgentInput
    ) -> AsyncGenerator[AgentEvent, None]:
        for event in self._script:
            yield event


class _PausedStateRepository:
    """Fake state repository returning a single state for the run by id."""

    def __init__(self, state: AgentState) -> None:
        self._state = state

    def get_or_none(self, state_id: str) -> AgentState | None:
        if state_id == self._state.id:
            return self._state
        return None


def _run_input() -> RunAgentInput:
    return RunAgentInput(
        state_id="run-1", instruction="do it", conversation_id="conv-1"
    )


def _driver(
    script: tuple[AgentEvent, ...],
    states: object | None = None,
) -> AgUiRunDriver:
    return AgUiRunDriver(
        runner=cast(AgentRunner, _ScriptedRunner(script, states)),
        run_input=_run_input(),
        agent_id="assistant",
        projector=AgUiProjector(AgUiConfig()),
        encoder=EventEncoder(),
    )


def _paused_state() -> AgentState:
    return AgentState(
        id="run-1",
        agent_type="assistant",
        status=AgentStatus.INTERRUPTED,
        transition=AgentStateTransition.WAITING_APPROVAL,
        reason=AgentStateReason.APPROVAL_REQUIRED,
        current_activity="Approve tool invocation: note_write",
        metadata={
            "approval": {
                "id": "approval:run-1:note.write",
                "allowed_decisions": ["approve", "reject"],
                "metadata": {"tool_name": "note_write"},
            }
        },
    )


async def test_driver_streams_ordered_sse_frames_with_finish_flush() -> None:
    """neutral event 스트림이 순서대로 SSE 프레임으로 흐르고 finish() flush가 닫는다."""
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            StepStartedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            MessageDeltaEvent(attribution=_ATTRIBUTION, message_id="m1", delta="hi"),
            ToolCallStartEvent(
                attribution=_ATTRIBUTION,
                call_id="c1",
                tool_name="lookup",
                parent_message_id="m1",
            ),
            ToolCallEndEvent(attribution=_ATTRIBUTION, call_id="c1"),
            ToolCallResultEvent(
                attribution=_ATTRIBUTION,
                call_id="c1",
                tool_name="lookup",
                message_id="m1",
                result={"answer": "ok"},
            ),
            StepFinishedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            RunFinishedEvent(attribution=_ATTRIBUTION),
        )
    )

    frames = [frame async for frame in driver]

    assert all(
        frame.startswith("data: ") and frame.endswith("\n\n") for frame in frames
    )
    types = [_event_type(frame) for frame in frames]
    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    # The text message END is flushed before the terminal RUN_FINISHED.
    assert types.index("TOOL_CALL_RESULT") < types.index("TEXT_MESSAGE_END")
    assert types[-1] == "RUN_FINISHED"


async def test_driver_flushes_open_message_when_stream_truncated() -> None:
    """종단 이벤트 없이 끝난 스트림도 driver의 projector.finish()가 열린 메시지를 닫는다."""
    driver = _driver(
        (MessageDeltaEvent(attribution=_ATTRIBUTION, message_id="m1", delta="hi"),)
    )

    frames = [frame async for frame in driver]
    types = [_event_type(frame) for frame in frames]

    assert types == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"]


async def test_driver_stateless_run_emits_no_pending_approval() -> None:
    """states가 None인 stateless run은 deferred-tool 승인 프레임을 내지 않는다."""
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            RunFinishedEvent(attribution=_ATTRIBUTION),
        ),
        states=None,
    )

    frames = [frame async for frame in driver]

    assert "hitl_approval" not in "".join(frames)
    assert _event_type(frames[-1]) == "RUN_FINISHED"


async def test_driver_durable_run_without_pending_approval_emits_no_frame() -> None:
    """durable run이지만 해당 run 상태가 없으면 승인 프레임을 내지 않는다."""
    other_state = AgentState(
        id="other", agent_type="assistant", status=AgentStatus.COMPLETED
    )
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            RunFinishedEvent(attribution=_ATTRIBUTION),
        ),
        states=_PausedStateRepository(other_state),
    )

    frames = [frame async for frame in driver]

    assert "hitl_approval" not in "".join(frames)


async def test_driver_surfaces_pending_approval_before_run_finished() -> None:
    """paused 상태가 있으면 deferred-tool 승인 프레임을 RUN_FINISHED 직전에 주입한다."""
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            StepStartedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            StepFinishedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            RunFinishedEvent(attribution=_ATTRIBUTION),
        ),
        states=_PausedStateRepository(_paused_state()),
    )

    frames = [frame async for frame in driver]
    types = [_event_type(frame) for frame in frames]
    text = "".join(frames)

    assert "hitl_approval" in text
    assert types.index("TOOL_CALL_START") < types.index("RUN_FINISHED")
    assert "TOOL_CALL_END" in types
    # The deferred approval is unresolved — no result frame is emitted.
    assert "TOOL_CALL_RESULT" not in types
    assert types[-1] == "RUN_FINISHED"


def _event_type(frame: str) -> str:
    return loads(frame.removeprefix("data: ").strip())["type"]
