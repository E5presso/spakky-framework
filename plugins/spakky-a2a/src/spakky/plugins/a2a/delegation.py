"""A2A-backed teammate delegation for ``@Agent`` teammate specs."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from a2a.types import (
    Message,
    Part,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import MessageToDict
from spakky.agent import (
    AgentDelegateTarget,
    AgentEvent,
    AgentEventAttribution,
    AgentYield,
    AgentYieldKind,
    ArtifactEvent,
    DelegationResult,
    DelegationToolResult,
    IAgentDelegate,
    MessageDeltaEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from spakky.agent.delegation import DelegationPacket
from spakky.agent.error import AgentToolDispatchError
from spakky.agent.types import JsonObject, JsonValue
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.a2a.client import A2ARemoteAgentClient, RemoteA2AMessage


class A2AStreamEventMapper:
    """Map remote A2A SDK stream responses into neutral child events."""

    def map(
        self,
        response: StreamResponse,
        packet: DelegationPacket,
    ) -> tuple[AgentEvent, ...]:
        """Project one SDK stream response onto neutral delegated events."""
        payload = response.WhichOneof("payload")
        if payload == "task":
            return self._task_events(response.task, packet)
        if payload == "message":
            return self._message_events(response.message, packet)
        if payload == "status_update":
            return self._status_events(response.status_update, packet)
        if payload == "artifact_update":
            return self._artifact_events(response.artifact_update, packet)
        return ()

    def _task_events(
        self,
        task: Task,
        packet: DelegationPacket,
    ) -> tuple[AgentEvent, ...]:
        attribution = _attribution(packet, task.id, task.context_id)
        events: list[AgentEvent] = [RunStartedEvent(attribution)]
        if task.status.state == TaskState.TASK_STATE_COMPLETED:
            events.append(RunFinishedEvent(attribution))
        if task.status.state == TaskState.TASK_STATE_FAILED:
            events.append(
                RunFinishedEvent(attribution, error=_state_error(task.status.state))
            )
        return tuple(events)

    def _message_events(
        self,
        message: Message,
        packet: DelegationPacket,
    ) -> tuple[AgentEvent, ...]:
        attribution = _attribution(
            packet, _run_id(packet, message.task_id), message.context_id
        )
        text = _message_text(message)
        if not text:
            return ()
        return (
            MessageDeltaEvent(
                attribution,
                message_id=message.message_id or f"{attribution.run_id}:message",
                delta=text,
            ),
        )

    def _status_events(
        self,
        update: TaskStatusUpdateEvent,
        packet: DelegationPacket,
    ) -> tuple[AgentEvent, ...]:
        attribution = _attribution(packet, update.task_id, update.context_id)
        events: list[AgentEvent] = []
        if update.status.state == TaskState.TASK_STATE_WORKING:
            events.append(StepStartedEvent(attribution, step_name="remote-a2a"))
            text = _message_text(update.status.message)
            if text:
                events.append(
                    MessageDeltaEvent(
                        attribution,
                        message_id=f"{update.task_id}:status",
                        delta=text,
                    )
                )
        if update.status.state == TaskState.TASK_STATE_COMPLETED:
            events.append(StepFinishedEvent(attribution, step_name="remote-a2a"))
            events.append(RunFinishedEvent(attribution))
        if update.status.state == TaskState.TASK_STATE_FAILED:
            events.append(
                RunFinishedEvent(attribution, error=_state_error(update.status.state))
            )
        return tuple(events)

    def _artifact_events(
        self,
        update: TaskArtifactUpdateEvent,
        packet: DelegationPacket,
    ) -> tuple[AgentEvent, ...]:
        attribution = _attribution(packet, update.task_id, update.context_id)
        artifact = update.artifact
        return (
            ArtifactEvent(
                attribution,
                artifact_id=artifact.artifact_id or f"{update.task_id}:artifact",
                name=artifact.name or None,
                content=[_part_value(part) for part in artifact.parts],
            ),
        )


@Pod()
@dataclass(frozen=True, slots=True)
class A2AAgentDelegate(IAgentDelegate):
    """Delegate remote teammate calls through the official A2A client."""

    client: A2ARemoteAgentClient = field(default_factory=A2ARemoteAgentClient)
    mapper: A2AStreamEventMapper = field(default_factory=A2AStreamEventMapper)

    async def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        """Execute a remote delegation packet and yield its terminal result."""
        tool_result = await self.delegate_tool_result(packet)
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=DelegationResult(
                id=f"{packet.id}:result",
                packet_id=packet.id,
                target=packet.target,
                summary=tool_result.summary,
                output=tool_result.output,
                metadata=tool_result.metadata,
            ),
        )

    async def delegate_tool_result(
        self,
        packet: DelegationPacket,
    ) -> DelegationToolResult:
        """Call a remote A2A teammate and return model result plus child events."""
        card_url = _card_url(packet.target)
        events: list[AgentEvent] = []
        final_task: Task | None = None
        final_status: TaskStatusUpdateEvent | None = None
        async for response in self.client.stream_message(
            card_url,
            RemoteA2AMessage(
                text=_instruction(packet),
                context_id=_conversation_id(packet),
            ),
        ):
            events.extend(self.mapper.map(response, packet))
            if response.WhichOneof("payload") == "task":
                final_task = response.task
            if response.WhichOneof("payload") == "status_update":
                final_status = response.status_update
        output = _task_output(final_task, final_status)
        return DelegationToolResult(
            summary=_summary(packet, output),
            output=output,
            events=tuple(events),
            metadata={"packet_id": packet.id, "card_url": card_url},
        )


def _card_url(target: AgentDelegateTarget) -> str:
    value = target.metadata.get("card_url")
    if not isinstance(value, str) or not value.strip():
        raise AgentToolDispatchError("Remote A2A delegation requires target card_url")
    return value


def _instruction(packet: DelegationPacket) -> str:
    value = packet.task.get("instruction")
    if not isinstance(value, str) or not value.strip():
        raise AgentToolDispatchError("Remote A2A delegation requires instruction")
    return value


def _conversation_id(packet: DelegationPacket) -> str | None:
    value = packet.metadata.get("conversation_id")
    return value if isinstance(value, str) and value.strip() else None


def _run_id(packet: DelegationPacket, candidate: str) -> str:
    return candidate if candidate.strip() else packet.id


def _attribution(
    packet: DelegationPacket,
    run_id: str,
    conversation_id: str,
) -> AgentEventAttribution:
    return AgentEventAttribution(
        agent_id=packet.target.agent_name or packet.target.agent_type,
        run_id=_run_id(packet, run_id),
        conversation_id=conversation_id if conversation_id.strip() else packet.id,
        parent_run_id=packet.parent_agent_state_id,
    )


def _message_text(message: Message) -> str:
    return "".join(
        part.text for part in message.parts if part.HasField("text") and part.text
    )


def _part_value(part: Part) -> JsonValue:
    if part.HasField("text"):
        return part.text
    if part.HasField("data"):
        return MessageToDict(part.data)
    if part.HasField("url"):
        return {"url": part.url}
    if part.HasField("raw"):
        return {"raw": part.raw.hex()}
    return {}


def _state_error(state: TaskState) -> JsonObject:
    return {"code": "remote_a2a_failed", "message": TaskState.Name(state)}


def _task_output(
    task: Task | None,
    status_update: TaskStatusUpdateEvent | None = None,
) -> JsonObject:
    if status_update is not None:
        return {
            "task_id": status_update.task_id,
            "context_id": status_update.context_id,
            "state": TaskState.Name(status_update.status.state),
        }
    if task is None:
        return {"task_id": None, "state": "unknown"}
    return {
        "task_id": task.id,
        "context_id": task.context_id,
        "state": TaskState.Name(task.status.state),
    }


def _summary(packet: DelegationPacket, output: JsonObject) -> str:
    state = output.get("state")
    return f"remote teammate '{packet.target.agent_name or packet.target.agent_type}' finished with {state}"
