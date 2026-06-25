"""Projection of neutral AgentEvent items onto A2A task events.

The runner's ``run_events()`` emits the protocol-neutral ``AgentEvent`` taxonomy
(ADR-0013 §3); this projector reproduces each event one-to-one as an a2a-sdk task
update. A2A 1.x parts are protobuf messages: text is ``Part(text=...)`` and
structured data is ``Part(data=<google.protobuf.Value>)``, built from a
JSON-compatible value via ``ParseDict``.

``RUN_FINISHED`` is not applied as a terminal transition here. The runner's
``run_events()`` always emits ``RUN_FINISHED`` even when a tool call paused on a
human approval gate, so the executor reconciles the real terminal state (complete,
fail, or input-required) once after draining the stream. This projector therefore
returns the run's terminal outcome rather than calling ``complete()`` itself.
"""

from dataclasses import dataclass

from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Value
from spakky.agent.event import (
    AgentEvent,
    AgentEventKind,
    ArtifactEvent,
    MessageDeltaEvent,
    ReasoningDeltaEvent,
    RunFinishedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.types import JsonObject, JsonValue

from spakky.plugins.a2a.error import UnsupportedAgentEventError


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Terminal result of one run, reconciled by the executor after draining.

    ``error`` is ``None`` for a successful run and carries the runner's terminal
    failure payload otherwise. The executor applies the single terminal task
    transition, since an approval pause must override a runner-reported success.
    """

    error: JsonObject | None


class AgentEventProjector:
    """Projects neutral AgentEvent items onto a2a-sdk task-event updates."""

    async def project(
        self,
        event: AgentEvent,
        updater: TaskUpdater,
    ) -> RunOutcome | None:
        """Publish A2A events for one agent event via the task updater.

        Args:
            event: The neutral event emitted by the agent runner.
            updater: The a2a-sdk updater bound to the running task.

        Returns:
            The run's terminal outcome for a ``RUN_FINISHED`` event, else None.

        Raises:
            UnsupportedAgentEventError: The event kind has no A2A projection.
        """
        match event.kind:
            case AgentEventKind.RUN_STARTED:
                await updater.start_work()
            case AgentEventKind.RUN_FINISHED:
                return RunOutcome(error=_as(event, RunFinishedEvent).error)
            case AgentEventKind.STEP_STARTED:
                await self._project_step(
                    _as(event, StepStartedEvent).step_name, updater
                )
            case AgentEventKind.STEP_FINISHED:
                await self._project_step(
                    _as(event, StepFinishedEvent).step_name, updater
                )
            case AgentEventKind.MESSAGE_DELTA:
                await self._project_message_delta(event, updater)
            case AgentEventKind.REASONING_DELTA:
                await self._project_reasoning_delta(event, updater)
            case AgentEventKind.TOOL_CALL_START:
                await self._project_tool_call_start(event, updater)
            case AgentEventKind.TOOL_CALL_ARGS_DELTA:
                await self._project_tool_call_args(event, updater)
            case AgentEventKind.TOOL_CALL_END:
                await self._project_tool_call_end(event, updater)
            case AgentEventKind.TOOL_CALL_RESULT:
                await self._project_tool_call_result(event, updater)
            case AgentEventKind.ARTIFACT:
                await self._project_artifact(event, updater)
            case AgentEventKind.STATE_SNAPSHOT:
                await self._project_state_snapshot(event, updater)
            case AgentEventKind.STATE_DELTA:
                await self._project_state_delta(event, updater)
            case _:  # pragma: no cover - exhaustive AgentEventKind StrEnum
                raise UnsupportedAgentEventError(str(event.kind))
        return None

    @staticmethod
    async def _project_step(step_name: str, updater: TaskUpdater) -> None:
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            metadata={"step_name": step_name},
        )

    @staticmethod
    async def _project_message_delta(event: AgentEvent, updater: TaskUpdater) -> None:
        message = _as(event, MessageDeltaEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            updater.new_agent_message(
                [Part(text=message.delta)],
                metadata={"message_id": message.message_id},
            ),
        )

    @staticmethod
    async def _project_reasoning_delta(event: AgentEvent, updater: TaskUpdater) -> None:
        reasoning = _as(event, ReasoningDeltaEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            updater.new_agent_message(
                [Part(text=reasoning.delta)],
                metadata={"reasoning_id": reasoning.reasoning_id, "reasoning": True},
            ),
        )

    @staticmethod
    async def _project_tool_call_start(event: AgentEvent, updater: TaskUpdater) -> None:
        start = _as(event, ToolCallStartEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            metadata={
                "tool_call": start.tool_name,
                "call_id": start.call_id,
                "phase": "start",
            },
        )

    @staticmethod
    async def _project_tool_call_args(event: AgentEvent, updater: TaskUpdater) -> None:
        args = _as(event, ToolCallArgsDeltaEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            metadata={"call_id": args.call_id, "args_delta": args.args_delta},
        )

    @staticmethod
    async def _project_tool_call_end(event: AgentEvent, updater: TaskUpdater) -> None:
        end = _as(event, ToolCallEndEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            metadata={"call_id": end.call_id, "phase": "end"},
        )

    @staticmethod
    async def _project_tool_call_result(
        event: AgentEvent, updater: TaskUpdater
    ) -> None:
        result = _as(event, ToolCallResultEvent)
        data = _data_part(
            {
                "tool": result.tool_name,
                "call_id": result.call_id,
                "result": result.result,
            }
        )
        await updater.add_artifact([data], name=result.tool_name)

    @staticmethod
    async def _project_artifact(event: AgentEvent, updater: TaskUpdater) -> None:
        artifact = _as(event, ArtifactEvent)
        name = artifact.name or artifact.artifact_id
        part = (
            Part(text=artifact.content)
            if isinstance(artifact.content, str)
            else _data_part_from_value(artifact.content)
        )
        await updater.add_artifact([part], name=name)

    @staticmethod
    async def _project_state_snapshot(event: AgentEvent, updater: TaskUpdater) -> None:
        snapshot = _as(event, StateSnapshotEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            updater.new_agent_message(
                [_data_part_from_value(snapshot.snapshot)],
                metadata={"state_snapshot": True},
            ),
        )

    @staticmethod
    async def _project_state_delta(event: AgentEvent, updater: TaskUpdater) -> None:
        delta = _as(event, StateDeltaEvent)
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            updater.new_agent_message(
                [_data_part_from_value(delta.patch)],
                metadata={"state_delta": True},
            ),
        )


def _data_part(payload: JsonObject) -> Part:
    """Build a protobuf data ``Part`` from a JSON-compatible mapping."""
    value = Value()
    ParseDict(dict(payload), value)
    return Part(data=value)


def _data_part_from_value(content: JsonValue) -> Part:
    """Build a protobuf data ``Part`` from any JSON-compatible value."""
    value = Value()
    # protobuf-stubs type ParseDict's js_dict as dict, but a Value target accepts
    # any JSON value (scalar, list, object) at runtime — the stub is too narrow.
    ParseDict(content, value)  # type: ignore[arg-type] - protobuf Value accepts any JSON value
    return Part(data=value)


def _as[EventT: AgentEvent](event: AgentEvent, event_type: type[EventT]) -> EventT:
    """Narrow an event to its declared member type.

    The runner pairs each ``AgentEventKind`` with a fixed event class, so a
    mismatch is an internal contract violation rather than a recoverable state.
    """
    if not isinstance(event, event_type):
        raise UnsupportedAgentEventError(event_type.__name__)
    return event
