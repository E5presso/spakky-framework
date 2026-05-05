"""Acceptance tests for the ADR-0009 CodeAssistant demo."""

from examples.code_assistant_demo import (
    CodeAssistantCommand,
    CodeAssistantResult,
    StaticModel,
    collect_stream,
)
from spakky.agent import (
    AgentEvidenceKind,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Approval,
    Cancel,
    Evidence,
    Final,
    ModelStreamEvent,
    ModelStreamEventKind,
    Progress,
    Token,
    Tool,
)
from spakky.agent.error import AgentDefinitionError
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeGit,
    FakeShell,
    FakeSignalRepository,
    FakeStateRepository,
    FakeWorkspace,
    RecordingModel,
    _approval_signal,
    _cancel_signal,
    _tool_call,
    _user_signal,
)


async def test_code_assistant_acceptance_expect_streaming_approval_signal_evidence_and_resume() -> (
    None
):
    """CodeAssistant demo가 stream/approval/signal/evidence/restart-resume을 end-to-end로 보인다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            _user_signal("run-1", "prefer the smaller patch"),
            _approval_signal("run-1", "approval:run-1:workspace.write"),
            _approval_signal("run-1", "approval:run-1:shell.command"),
        )
    )
    evidence = FakeEvidenceRepository()
    workspace = FakeWorkspace({"README.md": "hello agent"})
    shell = FakeShell()
    git = FakeGit()
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="planning",
            ),
            _tool_call("workspace.read", {"path": "README.md"}, "read-1"),
            _tool_call(
                "workspace.write",
                {"path": "notes.md", "content": "approved"},
                "write-1",
            ),
            _tool_call("shell.command", {"command": "printf ok"}, "shell-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    items = await collect_stream(
        model,
        workspace,
        shell,
        git,
        states,
        signals,
        evidence,
        CodeAssistantCommand(state_id="run-1", instruction="make a safe edit"),
    )

    assert _payload_count(items, Token) == 1
    assert _payload_count(items, Approval) == 2
    assert _payload_count(items, Tool) == 3
    assert _payload_count(items, Evidence) == 3
    assert workspace.files["notes.md"] == "approved"
    assert shell.commands == ("printf ok",)
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert {artifact.kind for artifact in evidence.list_by_state("run-1")} >= {
        AgentEvidenceKind.ACTION_BOUNDARY,
        AgentEvidenceKind.APPROVAL,
        AgentEvidenceKind.EVALUATION,
        AgentEvidenceKind.TOOL,
    }
    assert _final_payload(items).output == CodeAssistantResult(
        state_id="run-1",
        status="completed",
        tool_calls=("workspace.read", "workspace.write", "shell.command"),
        evidence_count=len(evidence.list_by_state("run-1")),
    )

    restarted_items = await collect_stream(
        StaticModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        workspace,
        shell,
        git,
        states,
        signals,
        evidence,
        CodeAssistantCommand(
            state_id="run-1",
            instruction="resume",
            resume=True,
        ),
    )

    assert restarted_items[0].kind is AgentYieldKind.PROGRESS
    assert isinstance(restarted_items[0].payload, Progress)
    assert "skip_completed" in restarted_items[0].payload.message


async def test_code_assistant_acceptance_expect_cancellation_terminal_state() -> None:
    """CodeAssistant demo cancel signal은 terminal state와 cancellation evidence를 남긴다."""
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
        CodeAssistantCommand(state_id="cancel-run", instruction="stop"),
    )

    assert len(items) == 1
    assert isinstance(items[0].payload, Cancel)
    assert states.get("cancel-run").status is AgentStatus.CANCELLED
    assert AgentEvidenceKind.CANCELLATION in {
        artifact.kind for artifact in evidence.list_by_state("cancel-run")
    }


def _payload_count(
    items: tuple[AgentYield[object], ...],
    payload_type: type[object],
) -> int:
    return sum(1 for item in items if isinstance(item.payload, payload_type))


def _final_payload(items: tuple[AgentYield[object], ...]) -> Final[CodeAssistantResult]:
    for item in reversed(items):
        if isinstance(item.payload, Final):
            return item.payload
    raise AgentDefinitionError("Missing final payload")
