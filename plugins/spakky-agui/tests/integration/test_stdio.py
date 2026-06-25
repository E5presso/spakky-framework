"""Integration: the AG-UI stdio boundary emits protocol JSON payloads."""

from collections.abc import AsyncIterator
from io import StringIO
from json import loads
from typing import override

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.encoder import EventEncoder

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunner,
    EvidenceCapture,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RunAgentInput,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.interfaces.model import IAgentModel

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.stdio import AgUiStdioCommand, run_agui_stdio
from spakky.plugins.agui.transport import AgUiRunDriver


@Agent(spec=AgentExecutionSpec(name="stdio_assistant", objective="answer with a tool"))
class StdioAssistant:
    """Stateless agent exercised through the stdio protocol boundary."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="lookup",
        description="Look up a fact.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def lookup(self, topic: str) -> str:
        """Look up a topic."""
        return f"fact:{topic}"


class _ScriptedModel(IAgentModel):
    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hello",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="lookup",
                arguments={"topic": "agents"},
                call_id="call-1",
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


def _run_agent_input_json() -> str:
    return (
        '{"threadId":"conv-1","runId":"run-1","state":null,'
        '"messages":[{"id":"u1","role":"user","content":"look up agents"}],'
        '"tools":[],"context":[],"forwardedProps":null}'
    )


def _run_driver_factory(
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]],
) -> RunDriverFactory:
    assistant = StdioAssistant(_ScriptedModel())
    config = AgUiConfig()

    def factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        captured.append((core_input, ag_ui_input, accept))
        runner = AgentRunner.for_agent_instance(assistant)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="stdio_assistant",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    return factory


def _event_types(output: StringIO) -> list[str]:
    return [loads(line)["type"] for line in output.getvalue().splitlines()]


async def test_stdio_streams_agui_event_payloads_from_argument() -> None:
    """문자열 인자로 받은 RunAgentInput이 stdout AG-UI JSON-lines로 스트리밍된다."""
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]] = []
    output = StringIO()

    await run_agui_stdio(
        run_driver_factory=_run_driver_factory(captured),
        input_stream=StringIO(""),
        output_stream=output,
        run_input_json=_run_agent_input_json(),
        accept="text/event-stream",
    )

    types = _event_types(output)
    assert "data: " not in output.getvalue()
    assert types[0] == "RUN_STARTED"
    assert "TOOL_CALL_RESULT" in types
    assert types[-1] == "RUN_FINISHED"
    assert captured[0][0].instruction == "look up agents"
    assert captured[0][0].state_id == "run-1"
    assert captured[0][2] == "text/event-stream"


async def test_stdio_command_reads_run_input_from_stdin() -> None:
    """등록 가능한 command callable은 stdin의 RunAgentInput을 소비한다."""
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]] = []
    output = StringIO()
    command = AgUiStdioCommand(
        run_driver_factory=_run_driver_factory(captured),
        input_stream=StringIO(_run_agent_input_json()),
        output_stream=output,
    )

    await command()

    types = _event_types(output)
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"
    assert captured[0][0].conversation_id == "conv-1"
