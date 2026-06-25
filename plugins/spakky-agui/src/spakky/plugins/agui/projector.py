"""Project neutral ``AgentEvent``s into AG-UI protocol events.

This is the fidelity-bearing half of the adapter. The neutral taxonomy carries
*deltas* (``MESSAGE_DELTA``, ``REASONING_DELTA``, ``TOOL_CALL_*``), but AG-UI
demands well-framed lifecycles: every text message is a
``TEXT_MESSAGE_START`` / ``…CONTENT`` / ``…END`` triple, every reasoning message
a ``REASONING_START`` / ``REASONING_MESSAGE_START`` / ``…CONTENT`` / ``…END`` /
``REASONING_END`` sequence, every tool call a
``TOOL_CALL_START`` / ``…ARGS`` / ``…END`` (with the result as a separate
``TOOL_CALL_RESULT``). The projector is the state machine that opens, continues,
and closes those frames as deltas arrive.

It is stateful for the span of one run: it tracks the currently open message,
the currently open reasoning message, and the set of open tool calls so that a
delta with a new id closes the previous frame, and so ``finish()`` can flush any
frame still open when the neutral stream ends (a truncated run stays well-formed
on the wire).
"""

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    MessagesSnapshotEvent,
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

from spakky.agent.event import (
    AgentEvent,
)
from spakky.agent.event import (
    ArtifactEvent as NeutralArtifactEvent,
)
from spakky.agent.event import (
    MessageDeltaEvent as NeutralMessageDeltaEvent,
)
from spakky.agent.event import (
    ReasoningDeltaEvent as NeutralReasoningDeltaEvent,
)
from spakky.agent.event import (
    RunFinishedEvent as NeutralRunFinishedEvent,
)
from spakky.agent.event import (
    RunStartedEvent as NeutralRunStartedEvent,
)
from spakky.agent.event import (
    StateDeltaEvent as NeutralStateDeltaEvent,
)
from spakky.agent.event import (
    StateSnapshotEvent as NeutralStateSnapshotEvent,
)
from spakky.agent.event import (
    StepFinishedEvent as NeutralStepFinishedEvent,
)
from spakky.agent.event import (
    StepStartedEvent as NeutralStepStartedEvent,
)
from spakky.agent.event import (
    ToolCallArgsDeltaEvent as NeutralToolCallArgsDeltaEvent,
)
from spakky.agent.event import (
    ToolCallEndEvent as NeutralToolCallEndEvent,
)
from spakky.agent.event import (
    ToolCallResultEvent as NeutralToolCallResultEvent,
)
from spakky.agent.event import (
    ToolCallStartEvent as NeutralToolCallStartEvent,
)

from spakky.agent.types import JsonObject, JsonValue

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.serialization import dump_json

ASSISTANT_ROLE = "assistant"
"""AG-UI text message role for model-authored assistant messages."""

REASONING_ROLE = "reasoning"
"""AG-UI reasoning message role required by ``REASONING_MESSAGE_START``."""

ARTIFACT_CUSTOM_EVENT_NAME = "artifact"
"""``CustomEvent`` name carrying a neutral artifact (no native AG-UI artifact)."""


class AgUiProjector:
    """Stateful per-run projector from neutral events to AG-UI events."""

    def __init__(self, config: AgUiConfig) -> None:
        self._config = config
        self._open_message_id: str | None = None
        self._open_reasoning_id: str | None = None
        # Insertion-ordered set of in-flight tool-call ids (dict keys, value unused)
        # so a truncated stream flushes END frames in a deterministic open order.
        self._open_tool_call_ids: dict[str, None] = {}

    def project(self, event: AgentEvent) -> list[BaseEvent]:
        """Project one neutral event into zero or more AG-UI events.

        The neutral ``kind`` field is typed ``AgentEventKind`` (not a per-class
        ``Literal``), so it does not narrow the union; matching on the event
        *type* does, which keeps each handler statically typed without casts.
        """
        match event:
            case NeutralMessageDeltaEvent():
                return self._project_message_delta(event)
            case NeutralReasoningDeltaEvent():
                return self._project_reasoning_delta(event)
            case NeutralToolCallStartEvent():
                return self._project_tool_start(event)
            case NeutralToolCallArgsDeltaEvent():
                return self._project_tool_args(event)
            case NeutralToolCallEndEvent():
                return self._project_tool_end(event)
            case NeutralToolCallResultEvent():
                return self._project_tool_result(event)
            case NeutralRunStartedEvent():
                return self._project_run_started(event)
            case NeutralRunFinishedEvent():
                return self._project_run_finished(event)
            case NeutralStepStartedEvent():
                return self._project_step_started(event)
            case NeutralStepFinishedEvent():
                return self._project_step_finished(event)
            case NeutralStateSnapshotEvent():
                return self._project_state_snapshot(event)
            case NeutralStateDeltaEvent():
                return self._project_state_delta(event)
            case NeutralArtifactEvent():  # pragma: no branch - exhaustive AgentEvent union
                return self._project_artifact(event)

    def finish(self) -> list[BaseEvent]:
        """Flush any open message, reasoning, or tool frames as END events.

        Called once after the neutral stream ends so a stream truncated mid-frame
        (no RUN_FINISHED, or a model that stopped mid-message) still produces a
        balanced AG-UI sequence on the wire.
        """
        return self._close_open_frames()

    def _project_message_delta(
        self, event: NeutralMessageDeltaEvent
    ) -> list[BaseEvent]:
        # Phase 1: a new message id closes the previous text/reasoning frame.
        events = self._open_text_message(event.message_id)
        # Phase 2: emit content only for a non-empty delta (AG-UI rejects empty).
        if event.delta:
            events.append(
                TextMessageContentEvent(message_id=event.message_id, delta=event.delta)
            )
        return events

    def _project_reasoning_delta(
        self, event: NeutralReasoningDeltaEvent
    ) -> list[BaseEvent]:
        events = self._open_reasoning_message(event.reasoning_id)
        if event.delta:
            events.append(
                ReasoningMessageContentEvent(
                    message_id=event.reasoning_id, delta=event.delta
                )
            )
        return events

    def _project_tool_start(self, event: NeutralToolCallStartEvent) -> list[BaseEvent]:
        self._open_tool_call_ids[event.call_id] = None
        parent_message_id = event.parent_message_id or self._open_message_id
        return [
            ToolCallStartEvent(
                tool_call_id=event.call_id,
                tool_call_name=event.tool_name,
                parent_message_id=parent_message_id,
            )
        ]

    def _project_tool_args(
        self, event: NeutralToolCallArgsDeltaEvent
    ) -> list[BaseEvent]:
        if not event.args_delta:
            return []
        return [ToolCallArgsEvent(tool_call_id=event.call_id, delta=event.args_delta)]

    def _project_tool_end(self, event: NeutralToolCallEndEvent) -> list[BaseEvent]:
        self._open_tool_call_ids.pop(event.call_id, None)
        return [ToolCallEndEvent(tool_call_id=event.call_id)]

    def _project_tool_result(
        self, event: NeutralToolCallResultEvent
    ) -> list[BaseEvent]:
        return [
            ToolCallResultEvent(
                message_id=event.message_id,
                tool_call_id=event.call_id,
                content=dump_json(event.result),
            )
        ]

    def _project_run_started(self, event: NeutralRunStartedEvent) -> list[BaseEvent]:
        attribution = event.attribution
        return [
            RunStartedEvent(
                thread_id=attribution.conversation_id,
                run_id=attribution.run_id,
                parent_run_id=attribution.parent_run_id,
            )
        ]

    def _project_run_finished(self, event: NeutralRunFinishedEvent) -> list[BaseEvent]:
        # Phase 1: close any frame still open before the terminal event.
        events = self._close_open_frames()
        # Phase 2: optionally emit a (currently empty) messages snapshot.
        if self._config.messages_snapshot_enabled:
            events.append(MessagesSnapshotEvent(messages=[]))
        # Phase 3: a carried error becomes RUN_ERROR, otherwise RUN_FINISHED.
        attribution = event.attribution
        if event.error is not None:
            events.append(
                RunErrorEvent(
                    message=_error_message(event.error),
                    code=_error_code(event.error),
                )
            )
            return events
        events.append(
            RunFinishedEvent(
                thread_id=attribution.conversation_id,
                run_id=attribution.run_id,
                result=event.metadata.get("output"),
            )
        )
        return events

    def _project_step_started(self, event: NeutralStepStartedEvent) -> list[BaseEvent]:
        return [StepStartedEvent(step_name=event.step_name)]

    def _project_step_finished(
        self, event: NeutralStepFinishedEvent
    ) -> list[BaseEvent]:
        return [StepFinishedEvent(step_name=event.step_name)]

    def _project_state_snapshot(
        self, event: NeutralStateSnapshotEvent
    ) -> list[BaseEvent]:
        if not self._config.emit_state_snapshot:
            return []
        return [StateSnapshotEvent(snapshot=event.snapshot)]

    def _project_state_delta(self, event: NeutralStateDeltaEvent) -> list[BaseEvent]:
        return [StateDeltaEvent(delta=list(_as_patch_operations(event.patch)))]

    def _project_artifact(self, event: NeutralArtifactEvent) -> list[BaseEvent]:
        return [
            CustomEvent(
                name=ARTIFACT_CUSTOM_EVENT_NAME,
                value={
                    "artifactId": event.artifact_id,
                    "name": event.name,
                    "content": event.content,
                },
            )
        ]

    def _open_text_message(self, message_id: str) -> list[BaseEvent]:
        if self._open_message_id == message_id:
            return []
        events = self._close_open_frames()
        self._open_message_id = message_id
        events.append(TextMessageStartEvent(message_id=message_id, role=ASSISTANT_ROLE))
        return events

    def _open_reasoning_message(self, reasoning_id: str) -> list[BaseEvent]:
        if self._open_reasoning_id == reasoning_id:
            return []
        events = self._close_open_frames()
        self._open_reasoning_id = reasoning_id
        events.append(ReasoningStartEvent(message_id=reasoning_id))
        events.append(
            ReasoningMessageStartEvent(message_id=reasoning_id, role=REASONING_ROLE)
        )
        return events

    def _close_open_frames(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if self._open_message_id is not None:
            events.append(TextMessageEndEvent(message_id=self._open_message_id))
            self._open_message_id = None
        if self._open_reasoning_id is not None:
            events.append(ReasoningMessageEndEvent(message_id=self._open_reasoning_id))
            events.append(ReasoningEndEvent(message_id=self._open_reasoning_id))
            self._open_reasoning_id = None
        # A tool call left open by a truncated stream (no TOOL_CALL_END) is closed
        # here in open order so the AG-UI sequence stays balanced on the wire.
        events.extend(
            ToolCallEndEvent(tool_call_id=call_id)
            for call_id in self._open_tool_call_ids
        )
        self._open_tool_call_ids.clear()
        return events


def _error_message(error: JsonObject) -> str:
    message = error.get("message")
    if isinstance(message, str):
        return message
    reason = error.get("reason")
    if isinstance(reason, str):
        return reason
    return dump_json(error)


def _error_code(error: JsonObject) -> str | None:
    code = error.get("code")
    if isinstance(code, str):
        return code
    return None


def _as_patch_operations(patch: JsonValue) -> list[JsonValue]:
    if isinstance(patch, list):
        return list(patch)
    return [patch]
