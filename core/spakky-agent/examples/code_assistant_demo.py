"""Claude Code-like CodeAssistant demo built from spakky-agent contracts."""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from subprocess import PIPE, run
from typing import override

from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentModel,
    IAgentSignalRepository,
    IAgentStateRepository,
    Agent,
    AgentActionBoundaryCheckpoint,
    AgentEvidence,
    AgentEvidenceCandidate,
    AgentEvidenceKind,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentApprovalRequest,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    ApprovalDecision,
    Cancel,
    Evidence,
    EvidenceCapture,
    Error,
    Final,
    Idempotency,
    JsonSchemaConstraint,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    Progress,
    RecoveryStrategy,
    SamplingOptions,
    Tool,
    ToolApprovalRequirement,
    ToolCallingSpec,
    ToolEffects,
    Token,
    agent_tool,
    begin_agent_cancellation,
    complete_agent_cancellation,
    materialize_agent_approval_decision_state,
    parse_agent_approval_decision_signal,
    plan_agent_resume,
    plan_agent_tool_approval,
    run_agent_cancellation_cleanup,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.tooling import AgentToolDescriptor


@dataclass(frozen=True, slots=True)
class CodeAssistantCommand:
    """Command DTO consumed by the CodeAssistant demo agent."""

    state_id: str
    instruction: str
    resume: bool = False


@dataclass(frozen=True, slots=True)
class CodeAssistantResult:
    """Final summary returned by the demo scenario."""

    state_id: str
    status: str
    tool_calls: tuple[str, ...]
    evidence_count: int


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
            stdout=PIPE,
            stderr=PIPE,
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
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(timeout_seconds=600),
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

    async def execute(
        self,
        command: CodeAssistantCommand,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Run one model-mediated coding-assistant scenario."""
        state = self._ensure_active_state(command)
        if command.resume:
            async for item in self._emit_resume_plan(state):
                yield item
            state = self._states.get(command.state_id)

        cancel = await self._consume_cancel(state)
        if cancel is not None:
            yield cancel
            return

        tool_calls: list[str] = []
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress("preparing model request", current_step="model"),
        )
        self._append_boundary(
            state.id,
            AgentActionBoundaryCheckpoint.before_model_call(
                "model:code_assistant_decision",
                idempotency=Idempotency.IDEMPOTENT,
            ),
        )
        request = self._model_request(command)
        async for event in self._model.stream(request):
            cancel = await self._consume_cancel(state)
            if cancel is not None:
                yield cancel
                return

            async for signal_item in self._consume_user_messages(state):
                yield signal_item

            if event.kind is ModelStreamEventKind.TOKEN_DELTA:
                yield AgentYield(
                    kind=AgentYieldKind.TOKEN,
                    payload=Token(event.token_delta or ""),
                )
            elif (
                event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE
                and event.tool_call is not None
            ):
                async for tool_item in self._execute_tool_call(state, event.tool_call):
                    yield tool_item
                if self._states.get(state.id).status is not AgentStatus.ACTIVE:
                    return
                tool_calls.append(event.tool_call.name)
            elif event.kind is ModelStreamEventKind.DONE:
                self._append_boundary(
                    state.id,
                    AgentActionBoundaryCheckpoint.after_model_call(
                        "model:code_assistant_decision",
                        idempotency=Idempotency.IDEMPOTENT,
                    ),
                )
            elif (
                event.kind is ModelStreamEventKind.ERROR
                and event.error is not None
            ):
                current_state = self._states.get(state.id)
                self._states.save(
                    replace(
                        current_state,
                        status=AgentStatus.FAILED,
                        transition=AgentStateTransition.FAILED,
                        reason=AgentStateReason.EXECUTION_FAILED,
                        current_activity="model stream failed",
                        metadata={
                            **current_state.metadata,
                            "model_error_code": event.error.code,
                        },
                    )
                )
                yield AgentYield(
                    kind=AgentYieldKind.ERROR,
                    payload=Error(
                        code=event.error.code,
                        message=event.error.message,
                        retryable=event.error.retryable,
                        metadata=event.error.metadata,
                    ),
                )
                return

        final_state = self._states.save(
            replace(
                self._states.get(state.id),
                status=AgentStatus.COMPLETED,
                transition=AgentStateTransition.COMPLETED,
                current_activity="demo completed",
            )
        )
        result = CodeAssistantResult(
            state_id=final_state.id,
            status=final_state.status.value,
            tool_calls=tuple(tool_calls),
            evidence_count=len(self._evidence.list_by_state(final_state.id)),
        )
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=result, metadata={"demo": "code_assistant"}),
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

    def _ensure_active_state(self, command: CodeAssistantCommand) -> AgentState:
        existing = self._states.get_or_none(command.state_id)
        if existing is not None:
            return self._states.save(
                replace(
                    existing,
                    status=AgentStatus.ACTIVE,
                    transition=AgentStateTransition.RUNNING,
                    current_activity=command.instruction,
                )
            )
        return self._states.save(
            AgentState(
                id=command.state_id,
                agent_type="CodeAssistant",
                status=AgentStatus.ACTIVE,
                transition=AgentStateTransition.RUNNING,
                current_activity=command.instruction,
                input_ref=command.instruction,
            )
        )

    async def _emit_resume_plan(
        self,
        state: AgentState,
    ) -> AsyncGenerator[AgentYield[object], None]:
        plan = plan_agent_resume(
            state,
            self._evidence.list_by_state(state.id),
            self._signals.list_pending(state.id),
        )
        self._states.save(plan.state)
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                f"resume action: {plan.action.value}",
                current_step="resume",
                metadata={
                    "requires_human_input": plan.requires_human_input,
                    "can_resume_automatically": plan.can_resume_automatically,
                },
            ),
        )

    def _model_request(self, command: CodeAssistantCommand) -> ModelRequest:
        tools = tuple(
            ModelToolSpec(
                name=descriptor.schema.name,
                description=descriptor.description,
                parameters=JsonSchemaConstraint(schema=descriptor.schema.input_schema),
                metadata={"tool_identity": descriptor.identity.key},
            )
            for descriptor in Agent.get(CodeAssistant).tool_catalog.descriptors
        )
        return ModelRequest(
            messages=(
                ModelMessage(
                    ModelMessageRole.SYSTEM,
                    "Use CodeAssistant tools for workspace, shell, and git actions.",
                ),
                ModelMessage(ModelMessageRole.USER, command.instruction),
            ),
            tool_calling=ToolCallingSpec(tools=tools, choice=ModelToolChoice.AUTO),
            sampling=SamplingOptions(temperature=0.0, max_tokens=512),
            metadata={"state_id": command.state_id, "demo": "code_assistant"},
        )

    async def _execute_tool_call(
        self,
        state: AgentState,
        call: ModelToolCall,
    ) -> AsyncGenerator[AgentYield[object], None]:
        descriptor = Agent.get(CodeAssistant).tool_catalog.by_schema_name(call.name)
        approval = plan_agent_tool_approval(
            descriptor=descriptor,
            approval_id=f"approval:{state.id}:{call.name}",
            agent_state_id=state.id,
            agent_type="CodeAssistant",
            call_id=call.call_id,
        )
        if approval.requires_approval and approval.yield_item is not None:
            self._append_boundary(
                state.id,
                AgentActionBoundaryCheckpoint.before_approval_wait(
                    f"approval:{call.name}",
                    metadata={"call_id": call.call_id or ""},
                ),
            )
            if approval.state is not None:
                self._states.save(approval.state)
            yield AgentYield[object](
                kind=approval.yield_item.kind,
                payload=approval.yield_item.payload,
            )
            if not self._consume_approval(state.id, approval.request):
                return
            self._append_boundary(
                state.id,
                AgentActionBoundaryCheckpoint.after_approval_wait(
                    f"approval:{call.name}",
                    metadata={"call_id": call.call_id or ""},
                ),
            )

        self._append_boundary(
            state.id,
            AgentActionBoundaryCheckpoint.before_tool_call(
                f"tool:{call.name}",
                idempotency=descriptor.metadata.idempotency,
                metadata={"call_id": call.call_id or ""},
            ),
        )
        result = self._invoke_tool(call)
        self._append_boundary(
            state.id,
            AgentActionBoundaryCheckpoint.after_tool_call(
                f"tool:{call.name}",
                idempotency=descriptor.metadata.idempotency,
                metadata={"call_id": call.call_id or ""},
            ),
        )
        evidence = self._append_tool_evidence(state.id, descriptor, result)
        yield AgentYield(
            kind=AgentYieldKind.TOOL,
            payload=Tool(
                name=call.name,
                call_id=call.call_id,
                arguments=call.arguments,
                result=result,
                metadata={"tool_identity": descriptor.identity.key},
            ),
        )
        yield AgentYield(
            kind=AgentYieldKind.EVIDENCE,
            payload=Evidence(evidence=evidence),
        )

    def _invoke_tool(self, call: ModelToolCall) -> JsonValue:
        if call.name == "workspace.read":
            return _workspace_read_result(
                self.workspace_read(_text_arg(call, "path")),
            )
        if call.name == "workspace.search":
            return _workspace_search_result(
                self.workspace_search(
                    _text_arg(call, "query"),
                    _optional_text_arg(call, "pattern") or "*",
                ),
            )
        if call.name == "workspace.write":
            return _workspace_write_result(
                self.workspace_write(
                    _text_arg(call, "path"),
                    _text_arg(call, "content"),
                ),
            )
        if call.name == "shell.command":
            return _shell_result(self.shell_command(_text_arg(call, "command")))
        if call.name == "git.status":
            return _git_json_result(self.git_status())
        if call.name == "git.diff":
            return _git_json_result(self.git_diff(_optional_text_arg(call, "path")))
        if call.name == "git.apply":
            return _git_json_result(self.git_apply(_text_arg(call, "patch")))
        raise CodeAssistantDemoError(f"Unknown CodeAssistant tool: {call.name}")

    def _append_tool_evidence(
        self,
        state_id: str,
        descriptor: AgentToolDescriptor,
        result: JsonValue,
    ) -> AgentEvidence:
        payload = result if isinstance(result, dict) else {"result": result}
        candidate = AgentEvidenceCandidate.tool_result(
            tool_identity=descriptor.identity.key,
            tool_schema_name=descriptor.schema.name,
            result=payload,
            capture=descriptor.metadata.evidence,
            summary=f"{descriptor.schema.name} completed",
        )
        return self._append_candidate(state_id, candidate)

    def _append_boundary(
        self,
        state_id: str,
        checkpoint: AgentActionBoundaryCheckpoint,
    ) -> AgentEvidence:
        return self._append_candidate(
            state_id,
            checkpoint.to_evidence_candidate(summary=checkpoint.action_id),
        )

    def _append_candidate(
        self,
        state_id: str,
        candidate: AgentEvidenceCandidate,
    ) -> AgentEvidence:
        index = len(self._evidence.list_by_state(state_id)) + 1
        return self._evidence.append(
            candidate.to_evidence(
                evidence_id=f"{state_id}:evidence:{index}",
                agent_state_id=state_id,
            )
        )

    async def _consume_user_messages(
        self,
        state: AgentState,
    ) -> AsyncGenerator[AgentYield[object], None]:
        for signal in self._signals.list_pending(state.id):
            if signal.kind is not AgentSignalKind.USER_MESSAGE:
                continue
            self._signals.mark_consumed(signal.id)
            self._append_candidate(
                state.id,
                AgentEvidenceCandidate(
                    kind=AgentEvidenceKind.EVALUATION,
                    payload={"signal_id": signal.id, "payload": signal.payload},
                    summary="user signal consumed",
                ),
            )
            yield AgentYield[object](
                kind=AgentYieldKind.PROGRESS,
                payload=Progress(
                    "user message consumed",
                    current_step="signal",
                    metadata={"signal_id": signal.id},
                ),
            )

    async def _consume_cancel(
        self,
        state: AgentState,
    ) -> AgentYield[object] | None:
        for signal in self._signals.list_pending(state.id):
            if signal.kind is not AgentSignalKind.CANCEL:
                continue
            self._signals.mark_consumed(signal.id)
            cancelling = self._states.save(begin_agent_cancellation(state, signal))
            report = await run_agent_cancellation_cleanup(
                state=cancelling,
                signal=signal,
                tasks=(),
            )
            self._append_candidate(
                state.id,
                report.to_evidence_candidate(summary="cancel cleanup completed"),
            )
            completed = self._states.save(
                complete_agent_cancellation(cancelling, report)
            )
            return AgentYield[object](
                kind=AgentYieldKind.CANCEL,
                payload=Cancel(
                    reason=completed.reason.value if completed.reason else None,
                    requested_by=_optional_signal_text(signal, "requested_by"),
                    metadata={"state": completed.status.value},
                ),
            )
        return None

    def _consume_approval(
        self,
        state_id: str,
        request: AgentApprovalRequest | None,
    ) -> bool:
        for signal in self._signals.list_pending(state_id):
            if signal.kind is not AgentSignalKind.APPROVAL_DECISION:
                continue
            if (
                request is not None
                and _optional_signal_text(
                    signal,
                    "request_id",
                )
                != request.id
            ):
                continue
            outcome = parse_agent_approval_decision_signal(signal, request=request)
            self._signals.mark_consumed(signal.id)
            current = self._states.get(state_id)
            next_state = materialize_agent_approval_decision_state(current, outcome)
            self._states.save(next_state)
            self._append_candidate(
                state_id,
                AgentEvidenceCandidate(
                    kind=AgentEvidenceKind.APPROVAL,
                    payload={
                        "signal_id": signal.id,
                        "request_id": outcome.request_id,
                        "decision": outcome.decision.value,
                    },
                    summary="approval decision consumed",
                ),
            )
            return outcome.decision in (
                ApprovalDecision.APPROVE,
                ApprovalDecision.MODIFY,
            )
        return False


def _git_result(operation: str, result: ShellCommandResult) -> GitCommandResult:
    return GitCommandResult(
        operation=operation,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _workspace_read_result(result: WorkspaceReadResult) -> dict[str, JsonValue]:
    return {"path": result.path, "content": result.content}


def _workspace_search_result(result: WorkspaceSearchResult) -> dict[str, JsonValue]:
    return {
        "query": result.query,
        "hits": tuple(
            {"path": hit.path, "line_number": hit.line_number, "line": hit.line}
            for hit in result.hits
        ),
    }


def _workspace_write_result(result: WorkspaceWriteResult) -> dict[str, JsonValue]:
    return {"path": result.path, "bytes_written": result.bytes_written}


def _shell_result(result: ShellCommandResult) -> dict[str, JsonValue]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _git_json_result(result: GitCommandResult) -> dict[str, JsonValue]:
    return {
        "operation": result.operation,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _text_arg(call: ModelToolCall, name: str) -> str:
    value = call.arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AgentDefinitionError(f"Model tool argument '{name}' must be text")
    return value


def _optional_text_arg(call: ModelToolCall, name: str) -> str | None:
    value = call.arguments.get(name)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_signal_text(signal: AgentSignal, name: str) -> str | None:
    value = signal.payload.get(name)
    if isinstance(value, str) and value.strip():
        return value
    return None


async def collect_stream(
    model: IAgentModel,
    workspace: IWorkspacePort,
    shell: IShellPort,
    git: IGitPort,
    states: IAgentStateRepository,
    signals: IAgentSignalRepository,
    evidence: IAgentEvidenceRepository,
    command: CodeAssistantCommand,
) -> tuple[AgentYield[object], ...]:
    """Small inbound-adapter-shaped collector for docs and tests."""
    agent = CodeAssistant(model, workspace, shell, git, states, signals, evidence)
    items: list[AgentYield[object]] = []
    async for item in agent.execute(command):
        items.append(item)
    return tuple(items)


class StaticModel(IAgentModel):
    """Tiny scripted model useful for the example module's smoke wiring."""

    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        self._events = tuple(events)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="static-demo")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        for event in self._events:
            yield event
