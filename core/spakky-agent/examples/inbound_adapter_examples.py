"""FastAPI WebSocket and Typer CLI inbound adapters for CodeAssistant.

The examples live with the demo application code, not in an agent-specific
plugin. They compose the existing FastAPI/Typer controller building blocks with
the `@Agent` business object that is already registered in the container.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
import json
from sys import stdin as process_stdin, stdout as process_stdout
from typing import TextIO, override
from uuid import uuid4

from examples.code_assistant_demo import CodeAssistant, CodeAssistantCommand
from fastapi import WebSocket
from spakky.agent import (
    IAgentSignalRepository,
    AgentSignal,
    AgentSignalKind,
    AgentYield,
    AgentYieldKind,
    Approval,
    ApprovalDecision,
    JsonObject,
    JsonValue,
)
from spakky.agent.error import AgentDefinitionError
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.fastapi.routes import websocket
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command


class InboundAdapterExampleError(Exception):
    """Raised when an inbound adapter example receives malformed input."""


class AgentJsonWebSocket(ABC):
    """Small surface the example needs from FastAPI WebSocket."""

    @abstractmethod
    async def send_json(self, data: object) -> None: ...

    @abstractmethod
    async def receive_json(self) -> object: ...


@ApiController("/agents")
class CodeAssistantWebSocketController(IContainerAware):
    """FastAPI WebSocket adapter for the CodeAssistant agent stream."""

    _container: IContainer | None = None

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @websocket("/code/ws")
    async def code_assistant(self, socket: WebSocket) -> None:
        await socket.accept()
        command = code_assistant_command_from_json(await socket.receive_json())
        await stream_code_assistant_to_websocket(
            _require_container(self._container),
            socket,
            command,
        )
        await socket.close()


@CliController("agents")
class CodeAssistantCliController(IContainerAware):
    """Typer CLI adapter for the CodeAssistant agent stream."""

    _container: IContainer | None = None

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @command("code", help="Run the CodeAssistant demo agent.")
    async def code_assistant(
        self,
        state_id: str,
        instruction: str,
        resume: bool = False,
        read_stdin_signal: bool = False,
    ) -> None:
        await stream_code_assistant_to_stdout(
            _require_container(self._container),
            CodeAssistantCommand(
                state_id=state_id,
                instruction=instruction,
                resume=resume,
            ),
            stdout=process_stdout,
            stdin=process_stdin,
            read_stdin_signal=read_stdin_signal,
        )


async def stream_code_assistant_to_websocket(
    container: IContainer,
    socket: AgentJsonWebSocket | WebSocket,
    command: CodeAssistantCommand,
) -> None:
    """Resolve CodeAssistant from the container and stream yields as JSON."""
    agent = container.get(CodeAssistant)
    signals = container.get(IAgentSignalRepository)
    async for item in agent.execute(command):
        await socket.send_json(agent_yield_to_event(item))
        if item.kind is AgentYieldKind.APPROVAL:
            signals.append(
                agent_signal_from_json(
                    command.state_id,
                    await socket.receive_json(),
                    approval=_approval_payload(item),
                )
            )


async def stream_code_assistant_to_stdout(
    container: IContainer,
    command: CodeAssistantCommand,
    *,
    stdout: TextIO,
    stdin: TextIO,
    read_stdin_signal: bool = False,
) -> None:
    """Resolve CodeAssistant and expose its AgentYield stream on stdout."""
    signals = container.get(IAgentSignalRepository)
    if read_stdin_signal:
        _append_signal_line(signals, command.state_id, stdin.readline())

    agent = container.get(CodeAssistant)
    async for item in agent.execute(command):
        event = agent_yield_to_event(item)
        if item.kind is AgentYieldKind.TOKEN:
            stdout.write(_event_text(event))
            stdout.flush()
        else:
            stdout.write(f"{event}\n")
            stdout.flush()
        if item.kind is AgentYieldKind.APPROVAL:
            _append_signal_line(
                signals,
                command.state_id,
                stdin.readline(),
                approval=_approval_payload(item),
            )


def code_assistant_command_from_json(payload: object) -> CodeAssistantCommand:
    """Build the command DTO from an inbound JSON payload."""
    data = _mapping(payload, "CodeAssistant command")
    state_id = _text(data, "state_id")
    instruction = _text(data, "instruction")
    resume = data.get("resume") is True
    return CodeAssistantCommand(
        state_id=state_id,
        instruction=instruction,
        resume=resume,
    )


def agent_yield_to_event(item: AgentYield[object]) -> dict[str, JsonValue]:
    """Encode one AgentYield into a transport-neutral JSON event."""
    return {
        "kind": item.kind.value,
        "payload": _json_value(item.payload),
    }


def agent_signal_from_json(
    state_id: str,
    payload: object,
    *,
    approval: Approval | None = None,
) -> AgentSignal:
    """Materialize an AgentSignal from WebSocket or stdin JSON payload."""
    data = _mapping(payload, "Agent signal")
    kind = _signal_kind(data)
    signal_payload = _signal_payload(kind, data, approval)
    return AgentSignal(
        id=_signal_id(state_id, kind, data, approval),
        agent_state_id=state_id,
        kind=kind,
        payload=signal_payload,
    )


def _append_signal_line(
    signals: IAgentSignalRepository,
    state_id: str,
    line: str,
    *,
    approval: Approval | None = None,
) -> None:
    text = line.strip()
    if not text:
        return
    signals.append(
        agent_signal_from_json(state_id, json.loads(text), approval=approval)
    )


def _event_text(event: Mapping[str, JsonValue]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return ""
    text = payload.get("text")
    if isinstance(text, str):
        return text
    return ""


def _signal_kind(data: Mapping[str, object]) -> AgentSignalKind:
    kind = data.get("kind")
    if kind == AgentSignalKind.APPROVAL_DECISION.value:
        return AgentSignalKind.APPROVAL_DECISION
    if kind == AgentSignalKind.CANCEL.value:
        return AgentSignalKind.CANCEL
    if kind in (None, AgentSignalKind.USER_MESSAGE.value):
        return AgentSignalKind.USER_MESSAGE
    raise InboundAdapterExampleError(f"Unsupported agent signal kind: {kind}")


def _signal_payload(
    kind: AgentSignalKind,
    data: Mapping[str, object],
    approval: Approval | None,
) -> JsonObject:
    if kind is AgentSignalKind.APPROVAL_DECISION:
        decision = _approval_decision(data)
        request_id = _optional_text(data, "request_id")
        if request_id is None and approval is not None:
            request_id = approval.id
        if request_id is None:
            raise InboundAdapterExampleError("Approval signal requires request_id")
        return {"request_id": request_id, "decision": decision.value}
    if kind is AgentSignalKind.CANCEL:
        return {"requested_by": _optional_text(data, "requested_by") or "user"}
    return {"message": _text(data, "message")}


def _approval_decision(data: Mapping[str, object]) -> ApprovalDecision:
    decision = _optional_text(data, "decision") or ApprovalDecision.APPROVE.value
    for candidate in ApprovalDecision:
        if candidate.value == decision:
            return candidate
    raise InboundAdapterExampleError(f"Unsupported approval decision: {decision}")


def _signal_id(
    state_id: str,
    kind: AgentSignalKind,
    data: Mapping[str, object],
    approval: Approval | None,
) -> str:
    signal_id = _optional_text(data, "id")
    if signal_id is not None:
        return signal_id
    if kind is AgentSignalKind.APPROVAL_DECISION and approval is not None:
        return approval.id
    return f"signal:{state_id}:{kind.value}:{uuid4().hex}"


def _approval_payload(item: AgentYield[object]) -> Approval:
    if isinstance(item.payload, Approval):
        return item.payload
    raise AgentDefinitionError("Approval yield must carry an Approval payload")


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return tuple(_json_value(item) for item in value)
    return str(value)


def _require_container(container: IContainer | None) -> IContainer:
    if container is None:
        raise InboundAdapterExampleError("Container was not injected")
    return container


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise InboundAdapterExampleError(f"{label} must be a JSON object")


def _text(data: Mapping[str, object], name: str) -> str:
    value = data.get(name)
    if isinstance(value, str) and value.strip():
        return value
    raise InboundAdapterExampleError(f"{name} must be non-empty text")


def _optional_text(data: Mapping[str, object], name: str) -> str | None:
    value = data.get(name)
    if isinstance(value, str) and value.strip():
        return value
    return None
