"""Claude Code-like CodeAssistant demo built from spakky-agent contracts.

ADR-0013 §1 hands the execution loop to the framework runner, so this demo
declares only an ``@Agent`` spec plus ``@agent_tool`` capabilities and one
``@on_signal`` hook — it carries no hand-written loop body. The runner-backed
``execute()`` is synthesized onto the class because no ``execute()`` is declared.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import run
from typing import override

from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentModel,
    IAgentSignalRepository,
    IAgentStateRepository,
    Agent,
    AgentExecutionSpec,
    AgentSignal,
    AgentSignalKind,
    AgentYield,
    AgentYieldKind,
    EvidenceCapture,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    Progress,
    RecoveryStrategy,
    RunAgentInput,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
    on_signal,
)


@dataclass(frozen=True, slots=True)
class WorkspaceSearchHit:
    """One workspace search hit."""

    path: str
    line_number: int
    line: str


@dataclass(frozen=True, slots=True)
class WorkspaceReadResult:
    """Result of reading a workspace file."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class WorkspaceSearchResult:
    """Result of searching workspace text."""

    query: str
    hits: tuple[WorkspaceSearchHit, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceWriteResult:
    """Result of writing a workspace file."""

    path: str
    bytes_written: int


@dataclass(frozen=True, slots=True)
class ShellCommandResult:
    """Captured shell command result."""

    command: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    """Captured git command result."""

    operation: str
    exit_code: int
    stdout: str
    stderr: str


class CodeAssistantDemoError(Exception):
    """Demo configuration or model-routing failure."""


class IWorkspacePort:
    """Workspace file-system capability injected into CodeAssistant."""

    def read_text(self, path: str) -> WorkspaceReadResult:
        """Read one text file from the workspace."""
        raise NotImplementedError

    def search_text(self, query: str, pattern: str = "*") -> WorkspaceSearchResult:
        """Search workspace text files."""
        raise NotImplementedError

    def write_text(self, path: str, content: str) -> WorkspaceWriteResult:
        """Write one text file in the workspace."""
        raise NotImplementedError


class IShellPort:
    """Local shell command capability injected into CodeAssistant."""

    def run(self, command: str) -> ShellCommandResult:
        """Run one shell command and capture output."""
        raise NotImplementedError


class IGitPort:
    """Git capability injected into CodeAssistant."""

    def status(self) -> GitCommandResult:
        """Return git status."""
        raise NotImplementedError

    def diff(self, path: str | None = None) -> GitCommandResult:
        """Return git diff."""
        raise NotImplementedError

    def apply_patch(self, patch: str) -> GitCommandResult:
        """Apply a git patch."""
        raise NotImplementedError


class LocalWorkspaceAdapter(IWorkspacePort):
    """Path-bounded workspace adapter for the demo."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @override
    def read_text(self, path: str) -> WorkspaceReadResult:
        target = self._resolve(path)
        return WorkspaceReadResult(path=path, content=target.read_text())

    @override
    def search_text(self, query: str, pattern: str = "*") -> WorkspaceSearchResult:
        hits: list[WorkspaceSearchHit] = []
        for target in sorted(self._root.rglob(pattern)):
            if not target.is_file():
                continue
            relative = target.relative_to(self._root).as_posix()
            for index, line in enumerate(target.read_text().splitlines(), start=1):
                if query in line:
                    hits.append(
                        WorkspaceSearchHit(
                            path=relative,
                            line_number=index,
                            line=line,
                        )
                    )
        return WorkspaceSearchResult(query=query, hits=tuple(hits))

    @override
    def write_text(self, path: str, content: str) -> WorkspaceWriteResult:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return WorkspaceWriteResult(path=path, bytes_written=len(content.encode()))

    def _resolve(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not target.is_relative_to(self._root):
            raise CodeAssistantDemoError("Workspace path escapes the configured root")
        return target


class SubprocessShellAdapter(IShellPort):
    """Subprocess-backed shell adapter for the demo."""

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    @override
    def run(self, command: str) -> ShellCommandResult:
        completed = run(
            command,
            cwd=self._cwd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        return ShellCommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class GitCliAdapter(IGitPort):
    """Git CLI adapter composed from the shell port."""

    def __init__(self, shell: IShellPort) -> None:
        self._shell = shell

    @override
    def status(self) -> GitCommandResult:
        return _git_result("status", self._shell.run("git status --short"))

    @override
    def diff(self, path: str | None = None) -> GitCommandResult:
        command = "git diff" if path is None else f"git diff -- {path}"
        return _git_result("diff", self._shell.run(command))

    @override
    def apply_patch(self, patch: str) -> GitCommandResult:
        quoted_patch = patch.replace("'", "'\"'\"'")
        return _git_result(
            "apply", self._shell.run(f"printf '%s' '{quoted_patch}' | git apply")
        )


@Agent(
    spec=AgentExecutionSpec(
        name="code_assistant",
        objective="demonstrate a Claude Code-like coding agent from framework parts",
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
            AgentSignalKind.RESUME,
            AgentSignalKind.STEERING_INSTRUCTION,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        delegation_allowed=True,
        metadata={"demo": "framework-building-block"},
    )
)
class CodeAssistant:
    """Framework building-block demo, not a packaged coding product."""

    def __init__(
        self,
        model: IAgentModel,
        workspace: IWorkspacePort,
        shell: IShellPort,
        git: IGitPort,
        states: IAgentStateRepository,
        signals: IAgentSignalRepository,
        evidence: IAgentEvidenceRepository,
    ) -> None:
        self._model = model
        self._workspace = workspace
        self._shell = shell
        self._git = git
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
    async def on_steering(
        self,
        signal: AgentSignal,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Echo a mid-run steering instruction back into the public stream."""
        instruction = signal.payload.get("instruction")
        text = instruction if isinstance(instruction, str) else ""
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                f"steering instruction: {text}",
                current_step="steering",
                metadata={"signal_id": signal.id},
            ),
        )

    @agent_tool(
        schema_name="workspace.read",
        description="Read a text file from the bounded workspace.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def workspace_read(self, path: str) -> WorkspaceReadResult:
        """Read a workspace file."""
        return self._workspace.read_text(path)

    @agent_tool(
        schema_name="workspace.search",
        description="Search text files in the bounded workspace.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def workspace_search(
        self,
        query: str,
        pattern: str = "*",
    ) -> WorkspaceSearchResult:
        """Search the workspace."""
        return self._workspace.search_text(query, pattern)

    @agent_tool(
        schema_name="workspace.write",
        description="Write a text file in the bounded workspace.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
    )
    def workspace_write(self, path: str, content: str) -> WorkspaceWriteResult:
        """Write a workspace file after approval."""
        return self._workspace.write_text(path, content)

    @agent_tool(
        schema_name="shell.command",
        description="Run a local shell command.",
        effects=ToolEffects.external_side_effect(),
        idempotency=Idempotency.NON_IDEMPOTENT,
        evidence=EvidenceCapture.SUMMARY,
    )
    def shell_command(self, command: str) -> ShellCommandResult:
        """Run an approved shell command."""
        return self._shell.run(command)

    @agent_tool(
        schema_name="git.status",
        description="Read git status.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def git_status(self) -> GitCommandResult:
        """Read git status."""
        return self._git.status()

    @agent_tool(
        schema_name="git.diff",
        description="Read git diff.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def git_diff(self, path: str | None = None) -> GitCommandResult:
        """Read git diff."""
        return self._git.diff(path)

    @agent_tool(
        schema_name="git.apply",
        description="Apply a patch to the worktree.",
        effects=ToolEffects.destructive_action(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.SUMMARY,
    )
    def git_apply(self, patch: str) -> GitCommandResult:
        """Apply a patch after approval."""
        return self._git.apply_patch(patch)


def _git_result(operation: str, result: ShellCommandResult) -> GitCommandResult:
    return GitCommandResult(
        operation=operation,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


async def collect_stream(
    model: IAgentModel,
    workspace: IWorkspacePort,
    shell: IShellPort,
    git: IGitPort,
    states: IAgentStateRepository,
    signals: IAgentSignalRepository,
    evidence: IAgentEvidenceRepository,
    run_input: RunAgentInput,
) -> tuple[AgentYield[object], ...]:
    """Small inbound-adapter-shaped collector for docs and tests."""
    agent = CodeAssistant(model, workspace, shell, git, states, signals, evidence)
    execute = vars(CodeAssistant)["execute"]
    items: list[AgentYield[object]] = []
    async for item in execute(agent, run_input):
        items.append(item)
    return tuple(items)


class StaticModel(IAgentModel):
    """Tiny scripted model useful for the example module's smoke wiring."""

    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        self._events = tuple(events)

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="static-demo")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        for event in self._events:
            yield event
