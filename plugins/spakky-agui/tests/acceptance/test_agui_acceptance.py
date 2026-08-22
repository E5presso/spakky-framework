"""Acceptance: a declared @Agent streams as a full neutral->ag_ui SSE run.

A CI-safe fake ``IAgentModel`` drives a declaration-only ``@Agent`` through the
framework runner via ``runner_backed_execute``, and the resulting public stream
is projected end to end (run_events -> projector -> EventEncoder) into AG-UI SSE
frames. The assertion fixes the developer-visible contract: a run surfaces as
``RUN_STARTED`` -> ``TEXT_MESSAGE_*`` -> ``TOOL_CALL_*`` -> ``RUN_FINISHED``.
"""

from collections.abc import AsyncIterator
from json import loads
from typing import override

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
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver


@Agent(
    spec=AgentExecutionSpec(
        name="agui_assistant",
        objective="answer with one tool",
    )
)
class AgUiAssistant:
    """Stateless declaration-only agent for the acceptance scenario."""

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
    """Fake model streaming a token then one tool call then done."""

    def __init__(self) -> None:
        self._request_count = 0

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        if self._request_count > 0:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="finished",
            )
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        self._request_count += 1
        call = ModelToolCall(
            name="lookup", arguments={"topic": "agents"}, call_id="call-1"
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="planning"
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_START, tool_call=call
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
            tool_call=call,
            tool_call_args_delta='{"topic":"agents"}',
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_END, tool_call=call)
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE, tool_call=call
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class _GoogleCandidateOnlyModel(IAgentModel):
    """Google-shaped stream emits only a terminal candidate for one tool call."""

    def __init__(self) -> None:
        self._request_count = 0

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_tools=True)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        if self._request_count > 0:
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        self._request_count += 1
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="lookup",
                arguments={"topic": "agents"},
                metadata={"thought_signature": "c2lnbmF0dXJl"},
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


async def test_declared_agent_streams_full_agui_sse_run() -> None:
    """선언형 @Agent가 RUN_STARTED→TEXT_MESSAGE_*→TOOL_CALL_*→RUN_FINISHED로 스트리밍된다."""
    run_input = RunAgentInput(
        state_id="run-1", instruction="look up agents", conversation_id="conv-1"
    )
    runner = AgentRunner.for_agent_instance(AgUiAssistant(_ScriptedModel()))
    driver = AgUiRunDriver(
        runner=runner,
        run_input=run_input,
        agent_id="agui_assistant",
        projector=AgUiProjector(AgUiConfig()),
        encoder=EventEncoder(),
    )

    frames = [loads(frame.removeprefix("data: ").strip()) async for frame in driver]
    types = [frame["type"] for frame in frames]

    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert types.index("TOOL_CALL_START") < types.index("TOOL_CALL_RESULT")
    assert types.count("TOOL_CALL_START") == 1
    assert types.count("TOOL_CALL_END") == 1
    starts = [
        frame["messageId"] for frame in frames if frame["type"] == "TEXT_MESSAGE_START"
    ]
    ends = [
        frame["messageId"] for frame in frames if frame["type"] == "TEXT_MESSAGE_END"
    ]
    assert starts == ["run-1:model-1:message", "run-1:model-2:message"]
    assert ends == starts
    for step, message_id in zip(("model-1", "model-2"), starts, strict=True):
        message_end = next(
            index
            for index, frame in enumerate(frames)
            if frame["type"] == "TEXT_MESSAGE_END" and frame["messageId"] == message_id
        )
        step_finished = next(
            index
            for index, frame in enumerate(frames)
            if frame["type"] == "STEP_FINISHED" and frame["stepName"] == step
        )
        assert message_end < step_finished
    assert types[-1] == "RUN_FINISHED"
    # Attribution flows end to end onto the AG-UI run frames.
    assert frames[0]["threadId"] == "conv-1"
    assert frames[0]["runId"] == "run-1"
    tool_result = next(f for f in frames if f["type"] == "TOOL_CALL_RESULT")
    assert tool_result["content"] == '"fact:agents"'


async def test_google_candidate_only_stream_synthesizes_one_agui_tool_frame() -> None:
    """Google candidate-only lifecycle becomes START→END→RESULT exactly once."""
    run_input = RunAgentInput(state_id="google-run", instruction="look up agents")
    driver = AgUiRunDriver(
        runner=AgentRunner.for_agent_instance(
            AgUiAssistant(_GoogleCandidateOnlyModel())
        ),
        run_input=run_input,
        agent_id="agui_assistant",
        projector=AgUiProjector(AgUiConfig()),
        encoder=EventEncoder(),
    )

    frames = [loads(frame.removeprefix("data: ").strip()) async for frame in driver]
    types = [frame["type"] for frame in frames]

    assert types.count("TOOL_CALL_START") == 1
    assert types.count("TOOL_CALL_END") == 1
    assert types.count("TOOL_CALL_RESULT") == 1
    assert types.index("TOOL_CALL_START") < types.index("TOOL_CALL_END")
    assert types.index("TOOL_CALL_END") < types.index("TOOL_CALL_RESULT")
    start = next(frame for frame in frames if frame["type"] == "TOOL_CALL_START")
    end = next(frame for frame in frames if frame["type"] == "TOOL_CALL_END")
    result = next(frame for frame in frames if frame["type"] == "TOOL_CALL_RESULT")
    assert start["toolCallId"] == end["toolCallId"] == result["toolCallId"]
