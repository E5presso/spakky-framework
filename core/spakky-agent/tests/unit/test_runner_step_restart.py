"""Runner tests for a model adapter asking to redo the current model step."""

from collections.abc import AsyncIterator, Mapping
from typing import override

import pytest

from spakky.agent import (
    AgentEvent,
    ArtifactEvent,
    AgentModelStepRestartError,
    AgentEvidenceKind,
    AgentExecutionLimits,
    AgentExecutionSpec,
    Agent,
    AgentRunner,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Error,
    Final,
    IAgentModel,
    JsonValue,
    MessageDeltaEvent,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
    Progress,
    RunAgentInput,
    RunFinishedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    StreamingExposureMode,
    Token,
    Tool,
    ToolCallResultEvent,
)
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingModel,
)
from tests.unit.test_runner import (
    DURABLE_SPEC,
    ProbeAgent,
    StatelessProbeAgent,
    _tool_event,
)

RESTART_CODE = "agent_model_step_restarted"


class _InterruptedOnceModel(RecordingModel):
    """Loses the first ``interruptions`` streams after a draft and a tool call."""

    def __init__(self, interruptions: int = 1, usage: ModelUsage | None = None) -> None:
        super().__init__(())
        self._interruptions = interruptions
        self._usage = usage

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) <= self._interruptions:
            raise self._restart()
        return ModelResponse(content="answer")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        if len(self.requests) <= self._interruptions:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="lost draft"
            )
            yield _tool_event("echo.read", {"value": "lost"}, "call-lost")
            raise self._restart()
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="answer"
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)

    def _restart(self) -> AgentModelStepRestartError:
        error = AgentModelStepRestartError()
        if self._usage is not None:
            error.attach_model_receipt(self._usage, {"model": "probe"})
        return error


@Agent(
    spec=AgentExecutionSpec(
        name="guarded_stateless_probe",
        streaming_exposure_mode=StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED,
    )
)
class _GuardedStatelessAgent:
    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Agent(
    spec=AgentExecutionSpec(
        name="limited_stateless_probe",
        limits=AgentExecutionLimits(max_steps=2),
    )
)
class _LimitedStatelessAgent:
    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Agent(
    spec=AgentExecutionSpec(
        name="token_limited_probe",
        accepted_signals=DURABLE_SPEC.accepted_signals,
        recovery=DURABLE_SPEC.recovery,
        limits=AgentExecutionLimits(max_tokens=5),
    )
)
class _TokenLimitedDurableAgent:
    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence


async def _yields(
    runner: AgentRunner, run_input: RunAgentInput
) -> tuple[AgentYield[object], ...]:
    return tuple([item async for item in runner.run(run_input)])


async def _events(
    runner: AgentRunner, run_input: RunAgentInput
) -> tuple[AgentEvent, ...]:
    return tuple([event async for event in runner.run_events(run_input)])


def _durable_runner(
    model: IAgentModel,
) -> tuple[AgentRunner, FakeStateRepository, FakeEvidenceRepository]:
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    agent = ProbeAgent(model, states, FakeSignalRepository(()), evidence)
    return AgentRunner.for_agent_instance(agent), states, evidence


def _mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    assert isinstance(value, Mapping)
    return value


def _invalidations(items: tuple[AgentYield[object], ...]) -> list[Progress]:
    return [
        item.payload
        for item in items
        if isinstance(item.payload, Progress)
        and item.payload.metadata.get("code") == RESTART_CODE
    ]


@pytest.mark.asyncio
async def test_runner_step_restart_stateless_yields_expect_step_redone_without_tool() -> (
    None
):
    """모델 어댑터가 단계 재시작을 알리면 버린 단계의 도구 호출을 실행하지 않고 다시 한다."""
    model = _InterruptedOnceModel()
    runner = AgentRunner.for_agent_instance(StatelessProbeAgent(model))

    items = await _yields(runner, RunAgentInput(state_id="run-1", instruction="go"))

    assert len(model.requests) == 2
    assert model.requests[0].messages == model.requests[1].messages
    assert not [item for item in items if isinstance(item.payload, Tool)]
    assert items[-1].kind is AgentYieldKind.FINAL
    tokens = [item.payload.text for item in items if isinstance(item.payload, Token)]
    assert tokens == ["lost draft", "answer"]
    (invalidation,) = _invalidations(items)
    assert invalidation.metadata["invalidate_output"] is True
    assert invalidation.current_step == "model-1"
    assert items.index(
        next(item for item in items if item.payload is invalidation)
    ) < items.index(
        next(
            item
            for item in items
            if isinstance(item.payload, Token) and item.payload.text == "answer"
        )
    )


@pytest.mark.asyncio
async def test_runner_step_restart_stateless_events_expect_step_closed_and_redone() -> (
    None
):
    """이벤트 표면도 버린 단계를 닫고 출력 무효화를 알린 뒤 새 단계를 시작한다."""
    model = _InterruptedOnceModel()
    runner = AgentRunner.for_agent_instance(StatelessProbeAgent(model))

    events = await _events(runner, RunAgentInput(state_id="run-1", instruction="go"))

    assert len(model.requests) == 2
    assert not [event for event in events if isinstance(event, ToolCallResultEvent)]
    steps = [
        (type(event), event.step_name)
        for event in events
        if isinstance(event, StepStartedEvent | StepFinishedEvent)
    ]
    assert steps == [
        (StepStartedEvent, "model-1"),
        (StepFinishedEvent, "model-1"),
        (StepStartedEvent, "model-2"),
        (StepFinishedEvent, "model-2"),
    ]
    (invalidation,) = [
        event
        for event in events
        if isinstance(event, ArtifactEvent)
        and event.metadata.get("code") == RESTART_CODE
    ]
    assert invalidation.metadata["invalidate_output"] is True
    deltas = [event.delta for event in events if isinstance(event, MessageDeltaEvent)]
    assert deltas == ["lost draft", "answer"]
    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is None


@pytest.mark.parametrize("events_surface", [False, True])
@pytest.mark.asyncio
async def test_runner_step_restart_durable_expect_discarded_step_recorded_not_replayed(
    events_surface: bool,
) -> None:
    """durable 실행은 버린 단계의 사용량과 경계를 증거로 남기고 transcript에는 넣지 않는다."""
    model = _InterruptedOnceModel(usage=ModelUsage(total_tokens=3))
    runner, states, evidence = _durable_runner(model)
    run_input = RunAgentInput(state_id="run-1", instruction="go")

    if events_surface:
        events = await _events(runner, run_input)
        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.error is None
    else:
        items = await _yields(runner, run_input)
        assert isinstance(items[-1].payload, Final)

    assert len(model.requests) == 2
    assert model.requests[0].messages == model.requests[1].messages
    assert states.get("run-1").status is AgentStatus.COMPLETED
    recorded = evidence.list_by_state("run-1")
    assert not [item for item in recorded if item.kind is AgentEvidenceKind.TOOL]
    first, second = [
        _mapping(item.payload["decision"])
        for item in recorded
        if item.kind is AgentEvidenceKind.MODEL
    ]
    assert (first["step"], second["step"]) == (1, 2)
    assert first["restarted"] is True
    assert "restarted" not in second
    assert _mapping(second["limits"])["total_tokens"] == 3


@pytest.mark.parametrize("events_surface", [False, True])
@pytest.mark.asyncio
async def test_runner_step_restart_guarded_complete_expect_step_redone(
    events_surface: bool,
) -> None:
    """complete() 경로에서 알린 재시작도 같은 단계를 다시 한다."""
    model = _InterruptedOnceModel()
    runner = AgentRunner.for_agent_instance(_GuardedStatelessAgent(model))
    run_input = RunAgentInput(state_id="run-1", instruction="go")

    if events_surface:
        events = await _events(runner, run_input)
        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.error is None
    else:
        items = await _yields(runner, run_input)
        assert items[-1].kind is AgentYieldKind.FINAL

    assert len(model.requests) == 2


@pytest.mark.parametrize("events_surface", [False, True])
@pytest.mark.asyncio
async def test_runner_step_restart_repeated_expect_bounded_by_step_limit(
    events_surface: bool,
) -> None:
    """재시작한 단계도 단계 수에 들어가므로 계속 재시작하는 모델은 한도에서 멈춘다."""
    model = _InterruptedOnceModel(interruptions=10)
    runner = AgentRunner.for_agent_instance(_LimitedStatelessAgent(model))
    run_input = RunAgentInput(state_id="run-1", instruction="go")

    if events_surface:
        events = await _events(runner, run_input)
        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.error is not None
        assert last.error["code"] == "agent_max_steps_exceeded"
    else:
        items = await _yields(runner, run_input)
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_max_steps_exceeded"

    assert len(model.requests) == 2


@pytest.mark.parametrize("events_surface", [False, True])
@pytest.mark.asyncio
async def test_runner_step_restart_usage_over_limit_expect_run_failed(
    events_surface: bool,
) -> None:
    """버린 단계의 사용량이 한도를 넘으면 다시 하지 않고 실패로 끝난다."""
    model = _InterruptedOnceModel(usage=ModelUsage(total_tokens=9))
    states = FakeStateRepository()
    agent = _TokenLimitedDurableAgent(
        model, states, FakeSignalRepository(()), FakeEvidenceRepository()
    )
    runner = AgentRunner.for_agent_instance(agent)
    run_input = RunAgentInput(state_id="run-1", instruction="go")

    if events_surface:
        events = await _events(runner, run_input)
        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.error is not None
        assert last.error["code"] == "agent_max_tokens_exceeded"
    else:
        items = await _yields(runner, run_input)
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_max_tokens_exceeded"

    assert len(model.requests) == 1
    assert states.get("run-1").status is AgentStatus.FAILED
