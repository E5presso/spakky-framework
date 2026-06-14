"""Tests for FastAPI/Typer inbound adapter examples."""

from collections.abc import Callable, Sequence
from io import StringIO
from typing import cast, overload

from examples.code_assistant_demo import CodeAssistant, CodeAssistantCommand
from examples.inbound_adapter_examples import (
    AgentJsonWebSocket,
    agent_signal_from_json,
    stream_code_assistant_to_stdout,
    stream_code_assistant_to_websocket,
)
from spakky.agent import (
    IAgentSignalRepository,
    AgentSignalKind,
    AgentYieldKind,
    JsonValue,
    ModelStreamEvent,
    ModelStreamEventKind,
)
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.interfaces.container import IContainer, NoSuchPodError
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeGit,
    FakeShell,
    FakeSignalRepository,
    FakeStateRepository,
    FakeWorkspace,
    RecordingModel,
    _tool_call,
)


async def test_fastapi_websocket_example_expect_streams_agent_yields_and_appends_approval() -> (
    None
):
    """WebSocket adapter resolves @Agent and forwards token/progress/approval/final."""
    signals = FakeSignalRepository(())
    container = RecordingContainer(_code_assistant(signals), signals)
    socket = RecordingWebSocket(
        (
            {
                "kind": "approval_decision",
                "decision": "approve",
            },
        )
    )

    await stream_code_assistant_to_websocket(
        container,
        socket,
        CodeAssistantCommand(state_id="ws-run", instruction="write approved note"),
    )

    assert container.resolved_types == (CodeAssistant, IAgentSignalRepository)
    assert _event_kinds(socket.sent) >= {
        AgentYieldKind.APPROVAL.value,
        AgentYieldKind.FINAL.value,
        AgentYieldKind.PROGRESS.value,
        AgentYieldKind.TOKEN.value,
    }
    assert signals.list_pending("ws-run") == ()


async def test_typer_cli_example_expect_stdout_streaming_and_stdin_user_signal_append() -> (
    None
):
    """Typer adapter streams to stdout and appends stdin user/approval signals."""
    signals = FakeSignalRepository(())
    container = RecordingContainer(_code_assistant(signals), signals)
    stdout = StringIO()
    stdin = StringIO(
        "".join(
            (
                '{"kind":"user_message","message":"keep it small"}\n',
                '{"kind":"approval_decision","decision":"approve"}\n',
            )
        )
    )

    await stream_code_assistant_to_stdout(
        container,
        CodeAssistantCommand(state_id="cli-run", instruction="write approved note"),
        stdout=stdout,
        stdin=stdin,
        read_stdin_signal=True,
    )

    output = stdout.getvalue()
    assert "thinking" in output
    assert "'kind': 'progress'" in output
    assert "'kind': 'approval'" in output
    assert "'kind': 'final'" in output
    assert container.resolved_types == (IAgentSignalRepository, CodeAssistant)
    assert signals.list_pending("cli-run") == ()


def test_agent_signal_from_json_expect_maps_user_message_to_appendable_signal() -> None:
    """Inbound JSON payloads become framework AgentSignal values."""
    signal = agent_signal_from_json(
        "run-1",
        {"kind": "user_message", "message": "please continue"},
    )

    assert signal.kind is AgentSignalKind.USER_MESSAGE
    assert signal.agent_state_id == "run-1"
    assert signal.payload == {"message": "please continue"}


def _code_assistant(signals: IAgentSignalRepository) -> CodeAssistant:
    return CodeAssistant(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta="thinking",
                ),
                _tool_call(
                    "workspace.write",
                    {"path": "notes.md", "content": "approved"},
                    "write-1",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        FakeWorkspace({}),
        FakeShell(),
        FakeGit(),
        FakeStateRepository(),
        signals,
        FakeEvidenceRepository(),
    )


def _event_kinds(events: Sequence[dict[str, JsonValue]]) -> set[str]:
    return {str(event["kind"]) for event in events}


class RecordingWebSocket(AgentJsonWebSocket):
    """WebSocket test double for JSON event streaming."""

    def __init__(self, incoming: Sequence[object]) -> None:
        self._incoming = tuple(incoming)
        self._index = 0
        self.sent: tuple[dict[str, JsonValue], ...] = ()

    async def send_json(self, data: object) -> None:
        if not isinstance(data, dict):
            raise NoSuchPodError
        self.sent = (*self.sent, data)

    async def receive_json(self) -> object:
        payload = self._incoming[self._index]
        self._index += 1
        return payload


class RecordingContainer(IContainer):
    """Container double that records CodeAssistant resolution."""

    def __init__(
        self,
        agent: CodeAssistant,
        signals: IAgentSignalRepository,
    ) -> None:
        self._agent = agent
        self._signals = signals
        self.resolved_types: tuple[type[object], ...] = ()

    @property
    def pods(self) -> dict[str, Pod]:
        return {}

    def add(self, obj: PodType) -> None:
        return None

    @overload
    def get[T: object](self, type_: type[T]) -> T: ...

    @overload
    def get[T: object](self, type_: type[T], name: str) -> T: ...

    def get[T: object](
        self,
        type_: type[T],
        name: str | None = None,
    ) -> T:
        self.resolved_types = (*self.resolved_types, type_)
        if type_ is CodeAssistant:
            return cast(T, self._agent)
        if type_ is IAgentSignalRepository:
            return cast(T, self._signals)
        raise NoSuchPodError

    @overload
    def get_or_none[T: object](self, type_: type[T]) -> T | None: ...

    @overload
    def get_or_none[T: object](self, type_: type[T], name: str) -> T | None: ...

    def get_or_none[T: object](
        self,
        type_: type[T],
        name: str | None = None,
    ) -> T | None:
        try:
            if name is None:
                return self.get(type_)
            return self.get(type_, name)
        except NoSuchPodError:
            return None

    def contains(self, type_: type, name: str | None = None) -> bool:
        return type_ in (CodeAssistant, IAgentSignalRepository)

    def find(self, selector: Callable[[Pod], bool]) -> set[object]:
        return set()
