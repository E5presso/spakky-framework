"""Protocol-neutral agent event taxonomy.

This taxonomy is the single neutral source that AG-UI, A2A, and MCP adapters
normalize into their respective protocols. The core stays protocol-neutral
(ADR-0013 §2 / §3): no event field is named after, or shaped by, any single
external protocol, yet every event carries enough attribution for each adapter
to reconstruct that protocol's linkage without loss.

Attribution carried by every event (ADR-0013 §3):

- ``agent_id`` — which agent emitted the event (team-mode composite attribution).
- ``run_id`` — the run this event belongs to. AG-UI projects this as ``runId``;
  A2A projects this as the A2A ``Task`` id.
- ``parent_run_id`` — the parent run in a delegation tree (``None`` for a root
  run that has no delegating parent). AG-UI projects this as ``parentRunId``;
  A2A projects this as the parent task in its task hierarchy.
- ``conversation_id`` — the multi-turn conversation this run participates in.
  AG-UI projects this as ``threadId``; A2A projects this as ``contextId``.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.state import AgentStateReason
from spakky.agent.types import JsonObject, JsonValue


class AgentEventKind(StrEnum):
    """Protocol-neutral event kinds emitted across an agent run.

    The lifecycle kinds (``RUN_STARTED`` … ``ARTIFACT``) generalize ADR-0009's
    public ``AgentYield`` vocabulary and align 1:1 with the streaming events that
    AG-UI and A2A adapters must reproduce (ADR-0013 §3).
    """

    MESSAGE_DELTA = "message_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS_DELTA = "tool_call_args_delta"
    TOOL_CALL_END = "tool_call_end"
    TOOL_CALL_RESULT = "tool_call_result"
    RUN_STARTED = "run_started"
    RUN_PAUSED = "run_paused"
    RUN_FINISHED = "run_finished"
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    STATE_SNAPSHOT = "state_snapshot"
    STATE_DELTA = "state_delta"
    ARTIFACT = "artifact"


@dataclass(frozen=True, slots=True)
class AgentEventAttribution:
    """Attribution carried by every protocol-neutral agent event.

    ``parent_run_id`` is ``None`` exactly when the run is a delegation-tree root
    (ADR-0013 §3 "parent link" / ADR-0009 parent linkage). The remaining ids are
    always present so adapters never have to synthesize linkage.
    """

    agent_id: str
    run_id: str
    conversation_id: str
    parent_run_id: str | None = None

    def __post_init__(self) -> None:
        """Reject attribution that cannot identify an agent, run, or conversation."""
        if not self.agent_id.strip():
            raise AgentDefinitionError("Agent event agent id cannot be blank")
        if not self.run_id.strip():
            raise AgentDefinitionError("Agent event run id cannot be blank")
        if not self.conversation_id.strip():
            raise AgentDefinitionError("Agent event conversation id cannot be blank")
        if self.parent_run_id is not None and not self.parent_run_id.strip():
            raise AgentDefinitionError("Agent event parent run id cannot be blank")


@dataclass(frozen=True, slots=True)
class MessageDeltaEvent:
    """Incremental assistant message text produced by the model."""

    attribution: AgentEventAttribution
    message_id: str
    delta: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.MESSAGE_DELTA, init=False)


@dataclass(frozen=True, slots=True)
class ReasoningDeltaEvent:
    """Incremental model reasoning (thinking) text."""

    attribution: AgentEventAttribution
    reasoning_id: str
    delta: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.REASONING_DELTA, init=False)


@dataclass(frozen=True, slots=True)
class ToolCallStartEvent:
    """A model has begun emitting a tool call with a known name.

    ``parent_message_id`` links the tool call to the assistant message that
    requested it (``None`` when the model emits the call outside any message).
    AG-UI projects this as ``parentMessageId`` on ``TOOL_CALL_START``.
    """

    attribution: AgentEventAttribution
    call_id: str
    tool_name: str
    parent_message_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.TOOL_CALL_START, init=False)


@dataclass(frozen=True, slots=True)
class ToolCallArgsDeltaEvent:
    """Incremental serialized arguments for an in-flight tool call."""

    attribution: AgentEventAttribution
    call_id: str
    args_delta: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(
        default=AgentEventKind.TOOL_CALL_ARGS_DELTA,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class ToolCallEndEvent:
    """A tool call has finished streaming its arguments."""

    attribution: AgentEventAttribution
    call_id: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.TOOL_CALL_END, init=False)


@dataclass(frozen=True, slots=True)
class ToolCallResultEvent:
    """The result returned by executing a completed tool call.

    ``message_id`` identifies the conversation message this tool result belongs
    to, so an adapter can attach the result to the right message. AG-UI requires
    it as ``messageId`` on ``TOOL_CALL_RESULT``; without it the result frame
    cannot be reconstructed losslessly.
    """

    attribution: AgentEventAttribution
    call_id: str
    tool_name: str
    message_id: str
    result: JsonValue = None
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.TOOL_CALL_RESULT, init=False)


@dataclass(frozen=True, slots=True)
class RunStartedEvent:
    """A run has started executing."""

    attribution: AgentEventAttribution
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.RUN_STARTED, init=False)


@dataclass(frozen=True, slots=True)
class RunPausedEvent:
    """A run has paused without terminal success or failure.

    The event is intentionally protocol-neutral: it carries core lifecycle
    reason plus the input prompt/decision envelope adapters need to project
    their own input-required or auth-required protocol states.
    """

    attribution: AgentEventAttribution
    reason: AgentStateReason
    prompt: str
    state_id: str
    approval_id: str | None = None
    tool_call_id: str | None = None
    allowed_decisions: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.RUN_PAUSED, init=False)

    def __post_init__(self) -> None:
        """Reject pause events that cannot be shown or resumed."""
        if not self.prompt.strip():
            raise AgentDefinitionError("Agent run pause prompt cannot be blank")
        if not self.state_id.strip():
            raise AgentDefinitionError("Agent run pause state id cannot be blank")
        if self.approval_id is not None and not self.approval_id.strip():
            raise AgentDefinitionError("Agent run pause approval id cannot be blank")
        if self.tool_call_id is not None and not self.tool_call_id.strip():
            raise AgentDefinitionError("Agent run pause tool call id cannot be blank")


@dataclass(frozen=True, slots=True)
class RunFinishedEvent:
    """A run has finished executing.

    ``error`` is ``None`` for a successful run and carries a terminal failure
    payload otherwise (A2A failed task / AG-UI ``RUN_ERROR``).
    """

    attribution: AgentEventAttribution
    error: JsonObject | None = None
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.RUN_FINISHED, init=False)


@dataclass(frozen=True, slots=True)
class StepStartedEvent:
    """A named step inside a run has started (one model-loop iteration)."""

    attribution: AgentEventAttribution
    step_name: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.STEP_STARTED, init=False)


@dataclass(frozen=True, slots=True)
class StepFinishedEvent:
    """A named step inside a run has finished."""

    attribution: AgentEventAttribution
    step_name: str
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.STEP_FINISHED, init=False)


@dataclass(frozen=True, slots=True)
class StateSnapshotEvent:
    """A full snapshot of shared run state."""

    attribution: AgentEventAttribution
    snapshot: JsonValue
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.STATE_SNAPSHOT, init=False)


@dataclass(frozen=True, slots=True)
class StateDeltaEvent:
    """An incremental change to shared run state.

    ``patch`` is a sequence of JSON-Patch operations (RFC 6902), the same shape
    AG-UI ``STATE_DELTA`` carries, so adapters relay it without re-deriving a diff.
    """

    attribution: AgentEventAttribution
    patch: JsonValue
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.STATE_DELTA, init=False)


@dataclass(frozen=True, slots=True)
class ArtifactEvent:
    """A produced artifact surfaced by an agent run."""

    attribution: AgentEventAttribution
    artifact_id: str
    content: JsonValue
    name: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    kind: AgentEventKind = field(default=AgentEventKind.ARTIFACT, init=False)


type AgentEvent = (
    MessageDeltaEvent
    | ReasoningDeltaEvent
    | ToolCallStartEvent
    | ToolCallArgsDeltaEvent
    | ToolCallEndEvent
    | ToolCallResultEvent
    | RunStartedEvent
    | RunPausedEvent
    | RunFinishedEvent
    | StepStartedEvent
    | StepFinishedEvent
    | StateSnapshotEvent
    | StateDeltaEvent
    | ArtifactEvent
)
"""Discriminated union of every protocol-neutral agent event.

Each member exposes a distinct ``kind`` literal so adapters dispatch with
``match``/``case`` exhaustiveness rather than runtime attribute probing.
"""
