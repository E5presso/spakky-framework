"""Tests for the CodeAssistant building-block demo."""

from collections.abc import AsyncIterator, Sequence
from typing import override

from examples.code_assistant_demo import (
    IGitPort,
    IShellPort,
    IWorkspacePort,
    CodeAssistant,
    CodeAssistantCommand,
    CodeAssistantResult,
    GitCommandResult,
    ShellCommandResult,
    StaticModel,
    WorkspaceReadResult,
    WorkspaceSearchHit,
    WorkspaceSearchResult,
    WorkspaceWriteResult,
    collect_stream,
)
from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
    Agent,
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Approval,
    ApprovalDecision,
    Cancel,
    Error,
    Evidence,
    Final,
    IAgentModel,
    JsonValue,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    Progress,
    Token,
    Tool,
)
from spakky.agent.error import AgentDefinitionError


def test_code_assistant_demo_expect_constructor_di_agent_and_expected_tools() -> None:
    """CodeAssistant demo가 @Agent와 @agent_tool catalog로 구성된다."""
    agent = Agent.get(CodeAssistant)

    assert agent.spec.name == "code_assistant"
    assert agent.required_persistence_repository_types() == (
        IAgentStateRepository,
        IAgentSignalRepository,
        IAgentEvidenceRepository,
    )
    assert set(agent.dependencies) >= {
        "model",
        "workspace",
        "shell",
        "git",
        "states",
        "signals",
        "evidence",
    }
    assert [
        descriptor.schema.name for descriptor in agent.tool_catalog.descriptors
    ] == [
        "git.apply",
        "git.diff",
        "git.status",
        "shell.command",
        "workspace.read",
        "workspace.search",
        "workspace.write",
    ]


async def test_code_assistant_demo_expect_runs_end_to_end_building_block_scenario() -> (
    None
):
    """vLLM-shaped stream, tools, approval, signal, evidence를 한 scenario로 검증한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="planning",
            ),
            _tool_call("workspace.read", {"path": "README.md"}, "read-1"),
            _tool_call(
                "workspace.search",
                {"query": "agent", "pattern": "*.md"},
                "search-1",
            ),
            _tool_call(
                "workspace.write",
                {"path": "notes.md", "content": "approved write"},
                "write-1",
            ),
            _tool_call("shell.command", {"command": "printf ok"}, "shell-1"),
            _tool_call("git.status", {}, "status-1"),
            _tool_call("git.diff", {"path": "notes.md"}, "diff-1"),
            _tool_call("git.apply", {"patch": "diff --git a/x b/x"}, "apply-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    workspace = FakeWorkspace({"README.md": "hello agent"})
    shell = FakeShell()
    git = FakeGit()
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            _user_signal("run-1", "please keep the diff small"),
            _approval_signal("run-1", "approval:run-1:workspace.write"),
            _approval_signal("run-1", "approval:run-1:shell.command"),
            _approval_signal("run-1", "approval:run-1:git.apply"),
        )
    )
    evidence = FakeEvidenceRepository()

    items = await collect_stream(
        model,
        workspace,
        shell,
        git,
        states,
        signals,
        evidence,
        CodeAssistantCommand(state_id="run-1", instruction="make a small edit"),
    )

    assert _kinds(items) == {
        AgentYieldKind.APPROVAL,
        AgentYieldKind.EVIDENCE,
        AgentYieldKind.FINAL,
        AgentYieldKind.PROGRESS,
        AgentYieldKind.TOKEN,
        AgentYieldKind.TOOL,
    }
    assert sum(1 for item in items if isinstance(item.payload, Approval)) == 3
    assert sum(1 for item in items if isinstance(item.payload, Tool)) == 7
    assert any(isinstance(item.payload, Token) for item in items)
    assert any(isinstance(item.payload, Evidence) for item in items)
    assert workspace.files["notes.md"] == "approved write"
    assert shell.commands == ("printf ok",)
    assert git.operations == ("status", "diff:notes.md", "apply")
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert {artifact.kind for artifact in evidence.list_by_state("run-1")} >= {
        AgentEvidenceKind.ACTION_BOUNDARY,
        AgentEvidenceKind.APPROVAL,
        AgentEvidenceKind.EVALUATION,
        AgentEvidenceKind.TOOL,
    }
    assert model.requests
    assert model.requests[0].tool_calling is not None
    assert [tool.name for tool in model.requests[0].tool_calling.tools] == [
        "git.apply",
        "git.diff",
        "git.status",
        "shell.command",
        "workspace.read",
        "workspace.search",
        "workspace.write",
    ]
    final_payload = _final_payload(items)

    assert final_payload.output == CodeAssistantResult(
        state_id="run-1",
        status="completed",
        tool_calls=(
            "workspace.read",
            "workspace.search",
            "workspace.write",
            "shell.command",
            "git.status",
            "git.diff",
            "git.apply",
        ),
        evidence_count=len(evidence.list_by_state("run-1")),
    )


async def test_code_assistant_demo_expect_cancellation_reaches_terminal_state() -> None:
    """cancel signal은 CANCELLING을 거쳐 CANCELLED와 evidence로 남는다."""
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()

    items = await collect_stream(
        StaticModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta="unused",
                ),
            )
        ),
        FakeWorkspace({}),
        FakeShell(),
        FakeGit(),
        states,
        FakeSignalRepository((_cancel_signal("cancel-run"),)),
        evidence,
        CodeAssistantCommand(state_id="cancel-run", instruction="stop now"),
    )

    assert len(items) == 1
    assert isinstance(items[0].payload, Cancel)
    assert states.get("cancel-run").status is AgentStatus.CANCELLED
    assert AgentEvidenceKind.CANCELLATION in {
        artifact.kind for artifact in evidence.list_by_state("cancel-run")
    }


async def test_code_assistant_demo_expect_model_stream_error_fails_state() -> None:
    """model ERROR events surface to callers instead of completing silently."""
    states = FakeStateRepository()

    items = await collect_stream(
        StaticModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.ERROR,
                    error=ModelError(
                        code="rate_limited",
                        message="provider rate limit",
                        retryable=True,
                        metadata={"provider": "test"},
                    ),
                ),
            )
        ),
        FakeWorkspace({}),
        FakeShell(),
        FakeGit(),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
        CodeAssistantCommand(state_id="error-run", instruction="trigger model error"),
    )

    assert [item.kind for item in items] == [
        AgentYieldKind.PROGRESS,
        AgentYieldKind.ERROR,
    ]
    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    error_payload = items[-1].payload
    assert isinstance(error_payload, Error)
    assert error_payload.code == "rate_limited"
    assert error_payload.retryable is True
    assert error_payload.metadata == {"provider": "test"}
    assert states.get("error-run").status is AgentStatus.FAILED


async def test_code_assistant_demo_expect_restart_resume_uses_persisted_boundaries() -> (
    None
):
    """restart 후 persisted state/evidence만으로 resume 계획을 stream에 노출한다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    workspace = FakeWorkspace({})
    shell = FakeShell()
    git = FakeGit()

    await collect_stream(
        StaticModel(
            (
                _tool_call("git.status", {}, "status-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        workspace,
        shell,
        git,
        states,
        signals,
        evidence,
        CodeAssistantCommand(state_id="resume-run", instruction="status"),
    )
    items = await collect_stream(
        StaticModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        workspace,
        shell,
        git,
        states,
        signals,
        evidence,
        CodeAssistantCommand(
            state_id="resume-run",
            instruction="resume",
            resume=True,
        ),
    )

    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and "skip_completed" in item.payload.message
        for item in items
    )


class RecordingModel(IAgentModel):
    """Scripted model that records the provider-neutral request."""

    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        self._events = tuple(events)
        self.requests: list[ModelRequest] = []

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content="recorded")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for event in self._events:
            yield event


class FakeWorkspace(IWorkspacePort):
    """Workspace test double."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)

    @override
    def read_text(self, path: str) -> WorkspaceReadResult:
        return WorkspaceReadResult(path=path, content=self.files[path])

    @override
    def search_text(self, query: str, pattern: str = "*") -> WorkspaceSearchResult:
        hits = tuple(
            WorkspaceSearchHit(path=path, line_number=1, line=content)
            for path, content in sorted(self.files.items())
            if query in content and (pattern == "*" or path.endswith(pattern[1:]))
        )
        return WorkspaceSearchResult(query=query, hits=hits)

    @override
    def write_text(self, path: str, content: str) -> WorkspaceWriteResult:
        self.files[path] = content
        return WorkspaceWriteResult(path=path, bytes_written=len(content.encode()))


class FakeShell(IShellPort):
    """Shell test double."""

    def __init__(self) -> None:
        self.commands: tuple[str, ...] = ()

    @override
    def run(self, command: str) -> ShellCommandResult:
        self.commands = (*self.commands, command)
        return ShellCommandResult(
            command=command,
            exit_code=0,
            stdout="ok",
            stderr="",
        )


class FakeGit(IGitPort):
    """Git test double."""

    def __init__(self) -> None:
        self.operations: tuple[str, ...] = ()

    @override
    def status(self) -> GitCommandResult:
        self.operations = (*self.operations, "status")
        return GitCommandResult("status", 0, " M notes.md", "")

    @override
    def diff(self, path: str | None = None) -> GitCommandResult:
        operation = "diff" if path is None else f"diff:{path}"
        self.operations = (*self.operations, operation)
        return GitCommandResult("diff", 0, "diff --git a/notes.md b/notes.md", "")

    @override
    def apply_patch(self, patch: str) -> GitCommandResult:
        self.operations = (*self.operations, "apply")
        return GitCommandResult("apply", 0, patch, "")


class FakeStateRepository(IAgentStateRepository):
    """State repository test double."""

    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    @override
    def get(self, state_id: str) -> AgentState:
        state = self.get_or_none(state_id)
        if state is None:
            raise AgentDefinitionError("Missing test state")
        return state

    @override
    def get_or_none(self, state_id: str) -> AgentState | None:
        return self._states.get(state_id)

    @override
    def save(self, state: AgentState) -> AgentState:
        self._states[state.id] = state
        return state

    @override
    def list_by_status(self, status: AgentStatus) -> Sequence[AgentState]:
        return tuple(state for state in self._states.values() if state.status is status)

    @override
    def list_resume_candidates(self) -> Sequence[AgentState]:
        return tuple(
            state
            for state in self._states.values()
            if state.status in (AgentStatus.ACTIVE, AgentStatus.INTERRUPTED)
        )


class FakeSignalRepository(IAgentSignalRepository):
    """Signal repository test double."""

    def __init__(self, signals: Sequence[AgentSignal]) -> None:
        self._signals = tuple(signals)
        self._consumed: set[str] = set()

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        self._signals = (*self._signals, signal)
        return signal

    @override
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(
            signal
            for signal in self._signals
            if signal.agent_state_id == state_id and signal.id not in self._consumed
        )

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        for signal in self._signals:
            if signal.id == signal_id:
                self._consumed.add(signal_id)
                return signal
        raise AgentDefinitionError("Missing test signal")


class FakeEvidenceRepository(IAgentEvidenceRepository):
    """Evidence repository test double."""

    def __init__(self) -> None:
        self._evidence: dict[str, AgentEvidence] = {}

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        self._evidence[evidence.id] = evidence
        return evidence

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise AgentDefinitionError("Missing test evidence")
        return evidence

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(
            artifact
            for artifact in self._evidence.values()
            if artifact.agent_state_id == state_id
        )

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        return tuple(
            artifact
            for artifact in self._evidence.values()
            if artifact.manifest_ref == manifest_ref
        )


def _tool_call(
    name: str,
    arguments: dict[str, JsonValue],
    call_id: str,
) -> ModelStreamEvent:
    return ModelStreamEvent(
        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        tool_call=ModelToolCall(name=name, arguments=arguments, call_id=call_id),
    )


def _user_signal(state_id: str, message: str) -> AgentSignal:
    return AgentSignal(
        id=f"user:{state_id}",
        agent_state_id=state_id,
        kind=AgentSignalKind.USER_MESSAGE,
        payload={"message": message},
    )


def _approval_signal(state_id: str, request_id: str) -> AgentSignal:
    return AgentSignal(
        id=request_id,
        agent_state_id=state_id,
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={
            "request_id": request_id,
            "decision": ApprovalDecision.APPROVE.value,
        },
    )


def _cancel_signal(state_id: str) -> AgentSignal:
    return AgentSignal(
        id=f"cancel:{state_id}",
        agent_state_id=state_id,
        kind=AgentSignalKind.CANCEL,
        payload={"reason": "user requested", "requested_by": "tester"},
    )


def _kinds(items: Sequence[AgentYield[object]]) -> set[AgentYieldKind]:
    return {item.kind for item in items}


def _final_payload(items: Sequence[AgentYield[object]]) -> Final[CodeAssistantResult]:
    for item in reversed(items):
        if isinstance(item.payload, Final):
            return item.payload
    raise AgentDefinitionError("Missing final payload")
