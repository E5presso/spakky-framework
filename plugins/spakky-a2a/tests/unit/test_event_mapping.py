"""Tests for projecting neutral AgentEvent items onto A2A task events."""

from collections.abc import Iterable

import pytest
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState
from google.protobuf.json_format import MessageToDict
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
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

from spakky.plugins.a2a.error import UnsupportedAgentEventError
from spakky.plugins.a2a.executor.event_mapping import AgentEventProjector, RunOutcome
from tests.unit.conftest import RecordingEventQueue

ATTRIBUTION = AgentEventAttribution(
    agent_id="assistant",
    run_id="task-1",
    conversation_id="ctx-1",
)


def _part_dicts(parts: Iterable[Part]) -> list[dict[str, object]]:
    return [MessageToDict(part) for part in parts]


async def _project(
    event: AgentEvent,
    updater: TaskUpdater,
) -> RunOutcome | None:
    return await AgentEventProjector().project(event, updater)


async def test_run_started_starts_work(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """RUN_STARTED transitions the task to working."""
    await _project(RunStartedEvent(ATTRIBUTION), updater)

    assert queue.status_updates()[0].status.state == TaskState.TASK_STATE_WORKING


async def test_run_finished_success_returns_outcome_without_error(
    updater: TaskUpdater,
) -> None:
    """RUN_FINISHED without error returns a success outcome for the executor."""
    outcome = await _project(RunFinishedEvent(ATTRIBUTION), updater)

    assert outcome == RunOutcome(error=None)


async def test_run_finished_error_returns_outcome_with_error(
    updater: TaskUpdater,
) -> None:
    """RUN_FINISHED with error returns a failure outcome for the executor."""
    outcome = await _project(
        RunFinishedEvent(ATTRIBUTION, error={"code": "boom", "message": "x"}),
        updater,
    )

    assert outcome == RunOutcome(error={"code": "boom", "message": "x"})


async def test_step_started_emits_working_with_step_name(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """STEP_STARTED emits a working status carrying the step name."""
    await _project(StepStartedEvent(ATTRIBUTION, step_name="model-call"), updater)

    status = queue.status_updates()[0]
    assert status.status.state == TaskState.TASK_STATE_WORKING
    assert status.metadata["step_name"] == "model-call"


async def test_step_finished_emits_working_with_step_name(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """STEP_FINISHED emits a working status carrying the step name."""
    await _project(StepFinishedEvent(ATTRIBUTION, step_name="model-call"), updater)

    assert queue.status_updates()[0].metadata["step_name"] == "model-call"


async def test_message_delta_streams_text(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """MESSAGE_DELTA streams the assistant text as a working status update."""
    await _project(
        MessageDeltaEvent(ATTRIBUTION, message_id="msg-1", delta="hello"),
        updater,
    )

    status = queue.status_updates()[0]
    assert status.status.state == TaskState.TASK_STATE_WORKING
    assert _part_dicts(status.status.message.parts) == [{"text": "hello"}]
    assert status.status.message.metadata["message_id"] == "msg-1"


async def test_reasoning_delta_streams_text_with_reasoning_flag(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """REASONING_DELTA streams reasoning text flagged distinctly from messages."""
    await _project(
        ReasoningDeltaEvent(ATTRIBUTION, reasoning_id="r-1", delta="thinking"),
        updater,
    )

    status = queue.status_updates()[0]
    assert MessageToDict(status.status.message.parts[0]) == {"text": "thinking"}
    assert status.status.message.metadata["reasoning"] is True


async def test_tool_call_start_emits_start_phase_metadata(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """TOOL_CALL_START emits a working status tagged with the start phase."""
    await _project(
        ToolCallStartEvent(ATTRIBUTION, call_id="c1", tool_name="search"),
        updater,
    )

    metadata = queue.status_updates()[0].metadata
    assert metadata["tool_call"] == "search"
    assert metadata["call_id"] == "c1"
    assert metadata["phase"] == "start"


async def test_tool_call_args_delta_emits_args_metadata(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """TOOL_CALL_ARGS_DELTA emits a working status carrying the args delta."""
    await _project(
        ToolCallArgsDeltaEvent(ATTRIBUTION, call_id="c1", args_delta='{"q":'),
        updater,
    )

    metadata = queue.status_updates()[0].metadata
    assert metadata["call_id"] == "c1"
    assert metadata["args_delta"] == '{"q":'


async def test_tool_call_end_emits_end_phase_metadata(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """TOOL_CALL_END emits a working status tagged with the end phase."""
    await _project(ToolCallEndEvent(ATTRIBUTION, call_id="c1"), updater)

    metadata = queue.status_updates()[0].metadata
    assert metadata["call_id"] == "c1"
    assert metadata["phase"] == "end"


async def test_tool_call_result_adds_named_data_artifact(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """TOOL_CALL_RESULT adds an artifact carrying the result named after the tool."""
    await _project(
        ToolCallResultEvent(
            ATTRIBUTION,
            call_id="c1",
            tool_name="search",
            message_id="msg-1",
            result={"hits": 2},
        ),
        updater,
    )

    artifact = queue.artifact_updates()[0].artifact
    assert artifact.name == "search"
    assert MessageToDict(artifact.parts[0].data) == {
        "tool": "search",
        "call_id": "c1",
        "result": {"hits": 2},
    }


async def test_artifact_str_content_adds_named_text_artifact(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """ARTIFACT with string content adds a text artifact under its name."""
    await _project(
        ArtifactEvent(ATTRIBUTION, artifact_id="a1", content="report", name="summary"),
        updater,
    )

    artifact = queue.artifact_updates()[0].artifact
    assert artifact.name == "summary"
    assert MessageToDict(artifact.parts[0]) == {"text": "report"}


async def test_artifact_structured_content_falls_back_to_artifact_id(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """ARTIFACT with structured content and no name uses the artifact id."""
    await _project(
        ArtifactEvent(ATTRIBUTION, artifact_id="a1", content={"k": "v"}),
        updater,
    )

    artifact = queue.artifact_updates()[0].artifact
    assert artifact.name == "a1"
    assert MessageToDict(artifact.parts[0].data) == {"k": "v"}


async def test_state_snapshot_emits_working_with_snapshot_data(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """STATE_SNAPSHOT emits a working status carrying the snapshot as data."""
    await _project(
        StateSnapshotEvent(ATTRIBUTION, snapshot={"count": 3}),
        updater,
    )

    status = queue.status_updates()[0]
    assert status.status.message.metadata["state_snapshot"] is True
    assert MessageToDict(status.status.message.parts[0].data) == {"count": 3}


async def test_state_delta_emits_working_with_patch_data(
    queue: RecordingEventQueue,
    updater: TaskUpdater,
) -> None:
    """STATE_DELTA emits a working status carrying the JSON patch as data."""
    await _project(
        StateDeltaEvent(ATTRIBUTION, patch=[{"op": "add", "path": "/x", "value": 1}]),
        updater,
    )

    status = queue.status_updates()[0]
    assert status.status.message.metadata["state_delta"] is True
    assert MessageToDict(status.status.message.parts[0].data) == [
        {"op": "add", "path": "/x", "value": 1}
    ]


async def test_event_type_mismatching_its_kind_raises(updater: TaskUpdater) -> None:
    """An event whose instance type mismatches its kind is rejected.

    The kind is forced to MESSAGE_DELTA on a ToolCallEndEvent, so the projector
    dispatches to the message-delta path and the type narrowing fails.
    """
    mismatched = ToolCallEndEvent(ATTRIBUTION, call_id="c1")
    object.__setattr__(
        mismatched,
        "kind",
        MessageDeltaEvent(ATTRIBUTION, message_id="m", delta="").kind,
    )

    with pytest.raises(UnsupportedAgentEventError):
        await _project(mismatched, updater)
