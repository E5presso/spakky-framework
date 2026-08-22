"""a2a-sdk ``AgentExecutor`` bound to a spakky @Agent instance.

Drives the framework-owned :class:`~spakky.agent.runner.AgentRunner` for one A2A
request over the neutral ``run_events()`` stream and projects each ``AgentEvent``
onto A2A task events. The A2A task id seeds the agent's durable ``state_id`` so a
human-approval pause resumes on the same run when the caller sends the next
message with the same task id and an approval-decision data part.

The runner emits approval/auth interruptions as first-class ``RunPausedEvent``
items, so the A2A projector maps those directly to ``input-required`` or
``auth-required``. This executor only reconciles ordinary ``RUN_FINISHED``
success/failure after the stream drains.
"""

from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass
from typing import cast, override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from spakky.agent import (
    AgentDefinitionError,
    AudioPart,
    DEFAULT_MEDIA_SAFETY_LIMITS,
    DocumentPart,
    ImagePart,
    VideoPart,
)
from spakky.agent.event import AgentEvent
from spakky.agent.execution import AgentSignalKind
from spakky.agent.inbound import RunAgentInput
from spakky.agent.interfaces.model import ModelSelection
from spakky.agent.interfaces.repository import (
    IAgentSignalRepository,
)
from spakky.agent.runner_factory import AgentRunnerFactory, IAgentRunnerFactory
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.types import JsonObject, JsonValue

from spakky.plugins.a2a.error import A2ARunResolutionError, InvalidApprovalDecisionError
from spakky.plugins.a2a.executor.event_mapping import AgentEventProjector, RunOutcome

APPROVAL_ID_PART_KEY = "approval_id"
"""Inbound data-part key carrying the approval request id to resume."""

APPROVAL_DECISION_PART_KEY = "decision"
"""Inbound data-part key carrying the chosen approval decision value."""

MODEL_SELECTION_PART_KEY = "modelSelection"
"""Inbound data-part key carrying a run-scoped model catalog reference."""

MODEL_REF_SELECTION_KEY = "modelRef"
"""Canonical model-selection key carrying the opaque model catalog reference."""

RUN_METADATA_PART_KEY = "metadata"
"""Inbound data-part key carrying extra core RunAgentInput metadata."""

MCP_PART_KEY = "mcp"
"""Inbound data-part key carrying runtime MCP server selectors."""

RUN_FAILED_FALLBACK_MESSAGE = "run failed"
"""Status message used when a failed run carries no error message."""


@dataclass(frozen=True, slots=True)
class _InboundApproval:
    """An approval id and decision parsed from an inbound A2A data part."""

    approval_id: str
    decision: ApprovalDecision


type _Attachment = ImagePart | AudioPart | VideoPart | DocumentPart


class SpakkyAgentExecutor(AgentExecutor):
    """Bridges A2A request execution onto the spakky agent event stream."""

    _agent: object
    _projector: AgentEventProjector
    _runner_factory: IAgentRunnerFactory

    def __init__(
        self,
        agent: object,
        projector: AgentEventProjector,
        runner_factory: IAgentRunnerFactory | None = None,
    ) -> None:
        self._agent = agent
        self._projector = projector
        self._runner_factory = runner_factory or AgentRunnerFactory()

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        approval = self._inbound_approval(context)
        current_task = context.current_task
        state_id = (
            current_task.id if current_task is not None else context.task_id or ""
        )
        conversation_id = (
            current_task.context_id if current_task is not None else context.context_id
        )
        run_input = RunAgentInput(
            state_id=state_id,
            instruction=self._instruction(context, approval is not None),
            conversation_id=conversation_id,
            resume=approval is not None,
            attachments=self._attachments(context),
            model_selection=self._model_selection(context),
            metadata=self._run_metadata(context),
        )
        task = await self._ensure_task(context, event_queue)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        if approval is not None:
            self._append_approval_signal(task.id, approval)
        outcome: RunOutcome | None = None
        async for event in self._run_events(run_input):
            projected = await self._projector.project(event, updater)
            if projected is not None:
                outcome = projected
        await self._reconcile_terminal(task.id, outcome, updater)

    async def _run_events(
        self,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Drive the runner's neutral event stream for one run."""
        async with self._runner_factory.open_runner(
            self._agent,
            run_input=run_input,
        ) as runner:
            async for event in runner.run_events(run_input):
                yield event

    async def _reconcile_terminal(
        self,
        _task_id: str,
        outcome: RunOutcome | None,
        updater: TaskUpdater,
    ) -> None:
        """Apply the single terminal A2A transition after draining the stream.

        A ``RUN_PAUSED`` event has already applied its non-terminal A2A state.
        Otherwise the run's outcome decides completion or failure.
        """
        if outcome is not None and outcome.paused:
            return
        if outcome is not None and outcome.error is not None:
            await self._project_run_failure(outcome.error, updater)
            return
        await updater.complete()

    @staticmethod
    async def _project_run_failure(error: JsonObject, updater: TaskUpdater) -> None:
        """Mark the task failed, surfacing the runner's terminal error payload."""
        message = error.get("message")
        await updater.update_status(
            TaskState.TASK_STATE_FAILED,
            updater.new_agent_message(
                [
                    Part(
                        text=message
                        if isinstance(message, str)
                        else RUN_FAILED_FALLBACK_MESSAGE
                    ),
                    _data_part(error),
                ]
            ),
        )

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        # Queue a durable cancel so an in-flight or resumed runner turn observes it,
        # then publish the canceled task state the A2A caller awaits in this turn.
        signals = self._signal_repository()
        if signals is not None:
            signals.append(
                AgentSignal(
                    id=f"cancel:{task_id}",
                    agent_state_id=task_id,
                    kind=AgentSignalKind.CANCEL,
                )
            )
        updater = TaskUpdater(event_queue, task_id, context.context_id or "")
        await updater.cancel()

    @staticmethod
    async def _ensure_task(context: RequestContext, event_queue: EventQueue) -> Task:
        """Return the resumed task or enqueue a freshly submitted one.

        The a2a-sdk requires a ``Task`` event before any status update, so a new
        run enqueues the submitted task before the updater publishes transitions.
        """
        if context.current_task is not None:
            return context.current_task
        task = Task(
            id=context.task_id or "",
            context_id=context.context_id or "",
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
        )
        await event_queue.enqueue_event(task)
        return task

    @staticmethod
    def _instruction(context: RequestContext, resume: bool = False) -> str:
        """Return the inbound user text, defaulting to a resume marker.

        A2A resume turns may carry only an approval data part with no text, but
        ``RunAgentInput`` rejects a blank instruction, so a non-blank marker seeds
        the resumed run whose real continuation comes from the durable signal.
        """
        instruction = context.get_user_input()
        if instruction.strip():
            return instruction
        if resume:
            return "resume"
        raise A2ARunResolutionError("message.text")

    @staticmethod
    def _attachments(context: RequestContext) -> tuple[_Attachment, ...]:
        """Map A2A raw/URL parts without interpreting structured data parts."""
        message = context.message
        if message is None:
            return ()
        attachments: list[_Attachment] = []
        total_inline_bytes = 0
        provenance = f"a2a:{message.message_id}"
        for part in message.parts:
            content_kind = part.WhichOneof("content")
            if content_kind in (None, "text", "data"):
                continue
            if len(attachments) >= DEFAULT_MEDIA_SAFETY_LIMITS.max_media_parts:
                raise A2ARunResolutionError("message.parts")
            if content_kind == "raw":
                total_inline_bytes += len(part.raw)
                if total_inline_bytes > DEFAULT_MEDIA_SAFETY_LIMITS.max_inline_bytes:
                    raise A2ARunResolutionError("message.parts")
            media_class = _media_class(part.media_type)
            try:
                if content_kind == "raw":
                    if media_class is DocumentPart:
                        attachments.append(
                            DocumentPart.from_bytes(
                                part.raw,
                                media_type=part.media_type,
                                filename=part.filename or None,
                                source=provenance,
                            )
                        )
                    else:
                        attachments.append(
                            media_class.from_bytes(
                                part.raw,
                                media_type=part.media_type,
                                source=provenance,
                            )
                        )
                elif content_kind == "url":
                    if media_class is DocumentPart:
                        attachments.append(
                            DocumentPart.from_uri(
                                part.url,
                                media_type=part.media_type,
                                filename=part.filename or None,
                                source=provenance,
                            )
                        )
                    else:
                        attachments.append(
                            media_class.from_uri(
                                part.url,
                                media_type=part.media_type,
                                source=provenance,
                            )
                        )
                else:
                    raise A2ARunResolutionError("message.parts")
            except AgentDefinitionError as error:
                raise A2ARunResolutionError("message.parts") from error
        return tuple(attachments)

    def _inbound_approval(
        self,
        context: RequestContext,
    ) -> "_InboundApproval | None":
        """Extract an approval id and decision from an inbound data part.

        The client echoes the ``approval_id`` it received on the pause; that id is
        the runner's approval request id, so it is preserved verbatim to match the
        pending approval rather than being re-derived from the task id.
        """
        for data in self._data_part_payloads(context):
            approval_id = data.get(APPROVAL_ID_PART_KEY)
            if not isinstance(approval_id, str):
                continue
            return _InboundApproval(
                approval_id=approval_id,
                decision=self._parse_decision(data.get(APPROVAL_DECISION_PART_KEY)),
            )
        return None

    def _model_selection(self, context: RequestContext) -> ModelSelection | None:
        """Extract one canonical run-scoped selector across all A2A data parts."""
        resolved: ModelSelection | None = None
        for data in self._data_part_payloads(context):
            if "model_selection" in data:
                raise A2ARunResolutionError(MODEL_SELECTION_PART_KEY)
            if MODEL_SELECTION_PART_KEY not in data:
                continue
            if resolved is not None:
                raise A2ARunResolutionError(MODEL_SELECTION_PART_KEY)
            value = data[MODEL_SELECTION_PART_KEY]
            if not isinstance(value, Mapping):
                raise A2ARunResolutionError(MODEL_SELECTION_PART_KEY)
            selection = cast(Mapping[str, object], value)
            if set(selection) != {MODEL_REF_SELECTION_KEY}:
                raise A2ARunResolutionError(MODEL_SELECTION_PART_KEY)
            model_ref = selection[MODEL_REF_SELECTION_KEY]
            if not isinstance(model_ref, str) or not model_ref.strip():
                raise A2ARunResolutionError("modelSelection.modelRef")
            resolved = ModelSelection(model_ref=model_ref)
        return resolved

    def _run_metadata(self, context: RequestContext) -> JsonObject:
        """Extract generic run metadata and runtime MCP selectors from A2A data."""
        metadata: dict[str, JsonValue] = {}
        for data in self._data_part_payloads(context):
            run_metadata = data.get(RUN_METADATA_PART_KEY)
            if run_metadata is not None:
                metadata.update(self._json_object(run_metadata, RUN_METADATA_PART_KEY))
            mcp = data.get(MCP_PART_KEY)
            if mcp is not None:
                metadata[MCP_PART_KEY] = self._json_object(mcp, MCP_PART_KEY)
        return metadata

    @staticmethod
    def _data_part_payloads(
        context: RequestContext,
    ) -> tuple[Mapping[str, object], ...]:
        """Return all inbound data parts as object mappings."""
        message = context.message
        if message is None:
            return ()
        payloads: list[Mapping[str, object]] = []
        for part in message.parts:
            if part.HasField("data"):
                payloads.append(cast(Mapping[str, object], MessageToDict(part.data)))
        return tuple(payloads)

    @staticmethod
    def _json_object(value: object, field: str) -> JsonObject:
        """Decode a JSON object from an A2A data part."""
        if not isinstance(value, Mapping):
            raise A2ARunResolutionError(field)
        return {
            key: cast(JsonValue, item)
            for key, item in cast(Mapping[object, object], value).items()
            if isinstance(key, str)
        }

    @staticmethod
    def _parse_decision(value: object) -> ApprovalDecision:
        """Narrow a raw decision value to a known ``ApprovalDecision``."""
        if not isinstance(value, str):
            raise InvalidApprovalDecisionError(str(value))
        try:
            return ApprovalDecision(value)
        except ValueError as e:
            raise InvalidApprovalDecisionError(value) from e

    def _append_approval_signal(
        self,
        task_id: str,
        approval: "_InboundApproval",
    ) -> None:
        """Append an APPROVAL_DECISION signal so the runner resumes the pause."""
        signals = self._signal_repository()
        if signals is None:
            raise InvalidApprovalDecisionError(approval.decision.value)
        signals.append(
            AgentSignal(
                id=f"approval:{approval.approval_id}",
                agent_state_id=task_id,
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={
                    "request_id": approval.approval_id,
                    "decision": approval.decision.value,
                },
            )
        )

    def _signal_repository(self) -> IAgentSignalRepository | None:
        """Resolve the agent's signal repository by type from its attributes.

        Mirrors ``AgentRunner.for_agent_instance``: constructor-injected ports are
        instance attributes, read from ``vars(instance)`` (not the banned
        ``getattr``) and matched by runtime type since attribute names vary.
        """
        return self._resolve(tuple(vars(self._agent).values()), IAgentSignalRepository)

    @staticmethod
    def _resolve[PortT](
        attributes: Sequence[object],
        port_type: type[PortT],
    ) -> PortT | None:
        for attribute in attributes:
            if isinstance(attribute, port_type):
                return attribute
        return None


def _data_part(payload: JsonObject) -> Part:
    """Build a protobuf data ``Part`` from a JSON-compatible mapping."""
    value = Value()
    ParseDict(dict(payload), value)
    return Part(data=value)


def _media_class(media_type: str) -> type[_Attachment]:
    """Choose one portable media part from an explicit MIME family."""
    if media_type.startswith("image/"):
        return ImagePart
    if media_type.startswith("audio/"):
        return AudioPart
    if media_type.startswith("video/"):
        return VideoPart
    if media_type.startswith(("application/", "text/")):
        return DocumentPart
    raise A2ARunResolutionError("message.parts.media_type")
