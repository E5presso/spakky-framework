"""Tests for the AG-UI SSE run driver consuming the neutral event stream."""

from collections.abc import AsyncGenerator, Sequence
from json import loads
from typing import cast

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.encoder import EventEncoder
from pytest import raises

from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    MessageDeltaEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.inbound import RunAgentInput
from spakky.agent.interfaces.repository import IAgentSignalRepository
from spakky.agent.runner import AgentRunner
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentStateReason

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint_input import (
    AgUiInboundRun,
    RESUME_APPROVAL_INSTRUCTION,
)
from spakky.plugins.agui.error import AgUiApprovalDecodeError
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiManagedRunDriver, AgUiRunDriver

_ATTRIBUTION = AgentEventAttribution(
    agent_id="assistant", run_id="run-1", conversation_id="conv-1"
)


class _ScriptedRunner:
    """Fake runner replaying a fixed neutral AgentEvent script over run_events."""

    def __init__(
        self,
        script: tuple[AgentEvent, ...],
        states: object | None = None,
        signals: IAgentSignalRepository | None = None,
    ) -> None:
        self._script = script
        self.states = states
        self.signals = signals

    async def run_events(
        self, run_input: RunAgentInput
    ) -> AsyncGenerator[AgentEvent, None]:
        for event in self._script:
            yield event


class _RunnerContext:
    def __init__(
        self,
        runner: _ScriptedRunner | None = None,
    ) -> None:
        self._runner = runner or _ScriptedRunner((), states=None)

    async def __aenter__(self) -> AgentRunner:
        return cast(AgentRunner, self._runner)

    async def __aexit__(self, *_: object) -> None:
        return None


class _FakeSignalRepository(IAgentSignalRepository):
    def __init__(self) -> None:
        self.appended: list[AgentSignal] = []

    def append(self, signal: AgentSignal) -> AgentSignal:
        self.appended.append(signal)
        return signal

    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(
            signal for signal in self.appended if signal.agent_state_id == state_id
        )

    def mark_consumed(self, signal_id: str) -> AgentSignal:
        return next(signal for signal in self.appended if signal.id == signal_id)


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


def _pause_event() -> RunPausedEvent:
    return RunPausedEvent(
        attribution=_ATTRIBUTION,
        reason=AgentStateReason.APPROVAL_REQUIRED,
        prompt="Approve tool invocation: note_write",
        state_id="run-1",
        approval_id="approval:run-1:note.write",
        tool_call_id="write-1",
        allowed_decisions=("approve", "reject"),
        metadata={"tool_name": "note_write"},
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


async def test_driver_run_without_pause_event_emits_no_approval_frame() -> None:
    """pause event가 없으면 승인 프레임을 내지 않는다."""
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            RunFinishedEvent(attribution=_ATTRIBUTION),
        )
    )

    frames = [frame async for frame in driver]

    assert "hitl_approval" not in "".join(frames)


async def test_driver_surfaces_pause_event_as_deferred_approval() -> None:
    """RunPausedEvent가 deferred-tool 승인 프레임으로 직접 투영된다."""
    driver = _driver(
        (
            RunStartedEvent(attribution=_ATTRIBUTION),
            StepStartedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            StepFinishedEvent(attribution=_ATTRIBUTION, step_name="model-call"),
            _pause_event(),
        )
    )

    frames = [frame async for frame in driver]
    types = [_event_type(frame) for frame in frames]
    text = "".join(frames)

    assert "hitl_approval" in text
    assert "TOOL_CALL_END" in types
    # The deferred approval is unresolved — no result frame is emitted.
    assert "TOOL_CALL_RESULT" not in types
    assert "RUN_FINISHED" not in types


async def test_managed_driver_requires_signal_repository_for_resume() -> None:
    """resume decision을 적재할 signal repository가 없으면 typed error다."""
    ag_ui_input = AgUiRunAgentInput.model_validate(
        {
            "threadId": "conv-1",
            "runId": "run-1",
            "state": None,
            "messages": [
                {
                    "id": "tool-1",
                    "role": "tool",
                    "content": (
                        '{"request_id":"approval:run-1:note.write",'
                        '"decision":"approve"}'
                    ),
                    "toolCallId": "approval:run-1:note.write",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": None,
        }
    )
    driver = AgUiManagedRunDriver(
        runner_context=_RunnerContext(),
        inbound=AgUiInboundRun(
            ag_ui_input=ag_ui_input,
            core_input=RunAgentInput(
                state_id="run-1",
                instruction=RESUME_APPROVAL_INSTRUCTION,
                conversation_id="conv-1",
                resume=True,
            ),
        ),
        agent_id="assistant",
        config=AgUiConfig(),
        accept=None,
    )

    with raises(AgUiApprovalDecodeError):
        _ = [frame async for frame in driver]


async def test_managed_driver_ingests_resume_decision_before_streaming() -> None:
    """resume decision은 runner stream 전 durable signal queue에 적재된다."""
    signals = _FakeSignalRepository()
    ag_ui_input = AgUiRunAgentInput.model_validate(
        {
            "threadId": "conv-1",
            "runId": "run-1",
            "state": None,
            "messages": [
                {
                    "id": "tool-1",
                    "role": "tool",
                    "content": (
                        '{"request_id":"approval:run-1:note.write",'
                        '"decision":"approve"}'
                    ),
                    "toolCallId": "approval:run-1:note.write",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": None,
        }
    )
    driver = AgUiManagedRunDriver(
        runner_context=_RunnerContext(
            _ScriptedRunner(
                (RunFinishedEvent(attribution=_ATTRIBUTION),),
                signals=signals,
            )
        ),
        inbound=AgUiInboundRun(
            ag_ui_input=ag_ui_input,
            core_input=RunAgentInput(
                state_id="run-1",
                instruction=RESUME_APPROVAL_INSTRUCTION,
                conversation_id="conv-1",
                resume=True,
            ),
        ),
        agent_id="assistant",
        config=AgUiConfig(),
        accept=None,
    )

    frames = [frame async for frame in driver]

    assert _event_type(frames[-1]) == "RUN_FINISHED"
    assert signals.appended[0].agent_state_id == "run-1"


def _event_type(frame: str) -> str:
    return loads(frame.removeprefix("data: ").strip())["type"]
