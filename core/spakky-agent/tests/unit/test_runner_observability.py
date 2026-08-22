"""Acceptance-level tests for Agent cost budgets and privacy-safe telemetry."""

from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import cast, override

import pytest

import spakky.agent.runner as runner_module
from spakky.agent import (
    AbstractAgentModelError,
    Agent,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentEvidence,
    AgentEvidenceKind,
    AgentRunner,
    AgentSpanKind,
    AgentSpanRecord,
    AgentSpanStatus,
    AgentTelemetryError,
    AgentYield,
    AgentYieldKind,
    Approval,
    Error,
    Final,
    IAgentModel,
    IAgentTelemetry,
    IRetriever,
    JsonObject,
    JsonValue,
    ModelPrice,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelPricingCatalog,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
    RetrievalContext,
    RetrievalHit,
    RecoveryStrategy,
    RunAgentInput,
    Tool,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.signal import AgentSignal, AgentSignalKind
from spakky.agent.state import AgentState, AgentStateTransition, AgentStatus
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)
from tests.unit.test_runner import (
    ContextProbeAgent,
    FrameworkFailingModel,
    FrameworkFailingToolProbeAgent,
    ProbeAgent,
    ScriptedRoundModel,
    StatelessProbeAgent,
    _collect,
    _tool_event,
)


class RecordingTelemetry(IAgentTelemetry):
    """In-memory observer with an explicit failure mode."""

    def __init__(self, *, fail: bool = False) -> None:
        self.records: list[AgentSpanRecord] = []
        self.fail = fail

    @override
    def record(self, span: AgentSpanRecord) -> None:
        if self.fail:
            raise RuntimeError("telemetry sink failed")
        self.records.append(span)


class ReceiptModelError(AbstractAgentModelError):
    """Typed post-provider failure carrying known billable model usage."""

    message = "post-provider operation failed"


class ReceiptFailingModel(IAgentModel):
    """Model that succeeds upstream, then raises with a billable receipt."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @staticmethod
    def _failure() -> ReceiptModelError:
        error = ReceiptModelError()
        error.attach_model_receipt(
            ModelUsage(input_tokens=10, output_tokens=2, total_tokens=12),
            {
                "model_ref": "model/logical",
                "profile": "primary",
                "provider": "test",
                "model": "physical",
                "cache_state": "failed",
            },
        )
        return error

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        _ = request
        raise self._failure()

    async def _events(self) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(kind=ModelStreamEventKind.PROGRESS)
        raise self._failure()

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        _ = request
        return self._events()


class ReceiptThenDoneModel(ReceiptFailingModel):
    """First call fails after billing; resumed call succeeds with new usage."""

    def __init__(self) -> None:
        self.calls = 0

    async def _events(self) -> AsyncIterator[ModelStreamEvent]:
        self.calls += 1
        if self.calls == 1:
            yield ModelStreamEvent(kind=ModelStreamEventKind.PROGRESS)
            raise self._failure()
        yield _done(usage=ModelUsage(input_tokens=10, output_tokens=2, total_tokens=12))


class StaticRetriever(IRetriever):
    """Deterministic scoped retriever for span coverage."""

    def __init__(self, hits: Sequence[RetrievalHit]) -> None:
        self._hits = tuple(hits)

    @override
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        return self._hits[:limit]


def _pricing(
    *,
    version: str = "prices-v1",
    input_rate: str = "1",
    output_rate: str = "2",
) -> ModelPricingCatalog:
    return ModelPricingCatalog(
        version=version,
        prices={
            "model/logical": ModelPrice(
                input_per_million=Decimal(input_rate),
                output_per_million=Decimal(output_rate),
                cached_input_per_million=Decimal("0.5"),
                cache_write_input_per_million=Decimal("1.5"),
            )
        },
    )


def _done(
    *,
    usage: ModelUsage | None = None,
    model_ref: str | None = "model/logical",
) -> ModelStreamEvent:
    metadata: dict[str, str] = {}
    if model_ref is not None:
        metadata = {
            "model_ref": model_ref,
            "profile": "vertex",
            "provider": "google",
            "model": "gemini-2.5-pro",
        }
    return ModelStreamEvent(
        kind=ModelStreamEventKind.DONE,
        usage=usage,
        metadata=metadata,
    )


@Agent(
    spec=AgentExecutionSpec(
        name="cost_limited", limits=AgentExecutionLimits(max_cost=Decimal("0.001"))
    )
)
class CostLimitedAgent:
    """Agent fixture enforcing an exact cumulative currency budget."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


class _ReceiptBudgetPorts:
    """Undecorated durable port holder reused by exhausted-budget fixtures."""

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


@Agent(
    spec=AgentExecutionSpec(
        name="receipt_cost_budget",
        accepted_signals=(AgentSignalKind.RESUME,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(max_cost=Decimal("0.000010")),
    )
)
class ReceiptCostBudgetAgent(_ReceiptBudgetPorts):
    """Durable fixture whose first billable error exhausts its cost budget."""


@Agent(
    spec=AgentExecutionSpec(
        name="receipt_token_budget",
        accepted_signals=(AgentSignalKind.RESUME,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(max_tokens=10),
    )
)
class ReceiptTokenBudgetAgent(_ReceiptBudgetPorts):
    """Durable fixture whose first billable error exhausts its token budget."""


async def test_model_receipt_error_complete_surface_remains_typed() -> None:
    """The provider-neutral error itself preserves its known usage receipt."""
    model = ReceiptFailingModel()

    with pytest.raises(ReceiptModelError) as raised:
        await model.complete(ModelRequest(messages=()))

    assert raised.value.model_usage == ModelUsage(
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
    )


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_agent_runner_accounts_post_provider_failure_receipt(
    surface: str,
) -> None:
    """Both runner surfaces persist billable usage/cost before terminal failure."""
    state_id = f"billable-model-error-{surface}"
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    telemetry = RecordingTelemetry()
    target = ProbeAgent(
        ReceiptFailingModel(),
        states,
        FakeSignalRepository(()),
        evidence,
    )
    runner = (
        AgentRunner.for_agent_instance(target)
        .with_pricing(_pricing())
        .with_telemetry(telemetry)
    )
    command = RunAgentInput(state_id=state_id, instruction="answer")

    if surface == "events":
        results: Sequence[AgentYield[object] | runner_module.AgentEvent] = [
            event async for event in runner.run_events(command)
        ]
        terminal = results[-1]
        assert isinstance(terminal, runner_module.RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.metadata["total_cost"] == "0.000014"
    else:
        results = await _collect(runner.run(command))
        terminal = results[-1]
        assert isinstance(terminal, AgentYield)
        assert isinstance(terminal.payload, Error)
        assert terminal.payload.metadata["total_cost"] == "0.000014"
    assert states.get(state_id).status is AgentStatus.FAILED
    model_evidence = next(
        item
        for item in evidence.list_by_state(state_id)
        if item.kind is AgentEvidenceKind.MODEL
    )
    decision = cast(Mapping[str, JsonValue], model_evidence.payload["decision"])
    usage = cast(Mapping[str, JsonValue], decision["usage"])
    assert usage["total_tokens"] == 12
    cost = cast(Mapping[str, JsonValue], decision["limits"])
    assert cost["total_cost"] == "0.000014"
    model_span = next(
        item for item in telemetry.records if item.kind is AgentSpanKind.MODEL
    )
    assert model_span.attributes["gen_ai.usage.total_tokens"] == 12
    assert model_span.attributes["gen_ai.usage.cost"] == "0.000014"


async def test_stateless_runner_accounts_post_provider_failure_receipt() -> None:
    """Receipt accounting does not depend on a durable evidence repository."""
    runner = AgentRunner.for_agent_instance(
        StatelessProbeAgent(ReceiptFailingModel())
    ).with_pricing(_pricing())

    items = await _collect(
        runner.run(RunAgentInput(state_id="stateless-receipt", instruction="answer"))
    )

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.metadata["total_cost"] == "0.000014"


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_receipt_failure_checkpoint_preserves_cost_across_fresh_resume(
    surface: str,
) -> None:
    """A billed failed step resumes at the next step with cumulative exact cost."""
    state_id = f"receipt-resume-{surface}"
    model = ReceiptThenDoneModel()
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    first_runner = AgentRunner.for_agent_instance(
        ProbeAgent(model, states, signals, evidence)
    ).with_pricing(_pricing())
    command = RunAgentInput(state_id=state_id, instruction="answer")
    if surface == "events":
        first: Sequence[AgentYield[object] | runner_module.AgentEvent] = [
            event async for event in first_runner.run_events(command)
        ]
        assert isinstance(first[-1], runner_module.RunFinishedEvent)
    else:
        first = await _collect(first_runner.run(command))
        assert isinstance(first[-1], AgentYield)
        assert isinstance(first[-1].payload, Error)
    assert states.get(state_id).metadata.get("runner_checkpoint") is not None
    resumed_runner = AgentRunner.for_agent_instance(
        ProbeAgent(model, states, signals, evidence)
    ).with_pricing(_pricing())
    resume = RunAgentInput(state_id=state_id, instruction="resume", resume=True)

    if surface == "events":
        resumed = [event async for event in resumed_runner.run_events(resume)]
        terminal = resumed[-1]
        assert isinstance(terminal, runner_module.RunFinishedEvent)
        assert terminal.error is None
        assert terminal.metadata["total_cost"] == "0.000028"
    else:
        resumed_yields = await _collect(resumed_runner.run(resume))
        final = resumed_yields[-1].payload
        assert isinstance(final, Final)
        assert final.metadata["total_cost"] == "0.000028"
    model_steps = [
        cast(Mapping[str, JsonValue], item.payload["decision"])["step"]
        for item in evidence.list_by_state(state_id)
        if item.kind is AgentEvidenceKind.MODEL
    ]
    assert model_steps == [1, 2]


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize(
    ("agent_type", "expected_code"),
    [
        (ReceiptCostBudgetAgent, "agent_max_cost_exceeded"),
        (ReceiptTokenBudgetAgent, "agent_max_tokens_exceeded"),
    ],
)
async def test_exhausted_receipt_budget_blocks_resumed_provider_io(
    surface: str,
    agent_type: type[_ReceiptBudgetPorts],
    expected_code: str,
) -> None:
    """A restored exhausted cost or token counter terminates before another call."""
    state_id = f"exhausted-{expected_code}-{surface}"
    model = ReceiptThenDoneModel()
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    first_runner = AgentRunner.for_agent_instance(
        agent_type(model, states, signals, evidence)
    ).with_pricing(_pricing())
    command = RunAgentInput(state_id=state_id, instruction="answer")
    if surface == "events":
        first: Sequence[AgentYield[object] | runner_module.AgentEvent] = [
            event async for event in first_runner.run_events(command)
        ]
        first_terminal = first[-1]
        assert isinstance(first_terminal, runner_module.RunFinishedEvent)
        assert first_terminal.error is not None
        assert first_terminal.error["code"] == expected_code
    else:
        first = await _collect(first_runner.run(command))
        first_terminal = first[-1]
        assert isinstance(first_terminal, AgentYield)
        assert isinstance(first_terminal.payload, Error)
        assert first_terminal.payload.code == expected_code
    resumed_runner = AgentRunner.for_agent_instance(
        agent_type(model, states, signals, evidence)
    ).with_pricing(_pricing())
    resume = RunAgentInput(state_id=state_id, instruction="resume", resume=True)

    if surface == "events":
        resumed = [event async for event in resumed_runner.run_events(resume)]
        terminal = resumed[-1]
        assert isinstance(terminal, runner_module.RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == expected_code
    else:
        resumed_yields = await _collect(resumed_runner.run(resume))
        terminal = resumed_yields[-1]
        assert isinstance(terminal.payload, Error)
        assert terminal.payload.code == expected_code
    assert model.calls == 1
    model_steps = [
        cast(Mapping[str, JsonValue], item.payload["decision"])["step"]
        for item in evidence.list_by_state(state_id)
        if item.kind is AgentEvidenceKind.MODEL
    ]
    assert model_steps == [1]


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_done_usage_limit_checkpoint_blocks_resumed_provider_io(
    surface: str,
) -> None:
    """Ordinary DONE usage errors persist counters before a fresh resume."""
    state_id = f"done-usage-exhausted-{surface}"
    model = ScriptedRoundModel(
        (
            (_done(usage=ModelUsage(input_tokens=10, total_tokens=12)),),
            (_done(usage=ModelUsage(total_tokens=1)),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    first_runner = AgentRunner.for_agent_instance(
        ReceiptTokenBudgetAgent(model, states, signals, evidence)
    )
    command = RunAgentInput(state_id=state_id, instruction="answer")
    if surface == "events":
        first = [event async for event in first_runner.run_events(command)]
        first_terminal = first[-1]
        assert isinstance(first_terminal, runner_module.RunFinishedEvent)
        assert first_terminal.error is not None
        assert first_terminal.error["code"] == "agent_max_tokens_exceeded"
    else:
        first_yields = await _collect(first_runner.run(command))
        first_error = first_yields[-1].payload
        assert isinstance(first_error, Error)
        assert first_error.code == "agent_max_tokens_exceeded"
    assert states.get(state_id).metadata.get("runner_checkpoint") is not None
    resumed_runner = AgentRunner.for_agent_instance(
        ReceiptTokenBudgetAgent(model, states, signals, evidence)
    )
    resume = RunAgentInput(state_id=state_id, instruction="resume", resume=True)

    if surface == "events":
        resumed = [event async for event in resumed_runner.run_events(resume)]
        terminal = resumed[-1]
        assert isinstance(terminal, runner_module.RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_max_tokens_exceeded"
    else:
        resumed_yields = await _collect(resumed_runner.run(resume))
        terminal = resumed_yields[-1].payload
        assert isinstance(terminal, Error)
        assert terminal.code == "agent_max_tokens_exceeded"
    assert len(model.requests) == 1


async def test_agent_runner_calculates_cost_and_records_safe_model_and_run_spans() -> (
    None
):
    """A successful run exposes exact cost without recording prompt or completion."""
    secret = "raw secret completion"
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta=secret,
                ),
                _done(
                    usage=ModelUsage(
                        input_tokens=1_000,
                        output_tokens=500,
                        total_tokens=1_500,
                        cached_input_tokens=200,
                        cache_write_input_tokens=100,
                        cache_write_5m_input_tokens=40,
                        cache_write_1h_input_tokens=60,
                    )
                ),
            ),
        )
    )
    telemetry = RecordingTelemetry()
    runner = (
        AgentRunner.for_agent_instance(StatelessProbeAgent(model))
        .with_pricing(_pricing())
        .with_telemetry(telemetry)
    )

    items = await _collect(
        runner.run(
            RunAgentInput(
                state_id="priced-run",
                instruction="raw secret prompt",
            )
        )
    )

    final = cast(Final[object], items[-1].payload)
    assert final.metadata["total_cost"] == "0.00195"
    assert final.metadata["cost_currency"] == "USD"
    assert final.metadata["pricing_version"] == "prices-v1"
    assert [record.kind for record in telemetry.records] == [
        AgentSpanKind.MODEL,
        AgentSpanKind.RUN,
    ]
    model_span, run_span = telemetry.records
    assert model_span.status is AgentSpanStatus.OK
    assert model_span.attributes["model_ref"] == "model/logical"
    assert model_span.attributes["profile"] == "vertex"
    assert model_span.attributes["provider"] == "google"
    assert model_span.attributes["gen_ai.usage.input_tokens"] == 1_000
    assert model_span.attributes["gen_ai.usage.cached_input_tokens"] == 200
    assert model_span.attributes["gen_ai.usage.cache_write_5m_input_tokens"] == 40
    assert model_span.attributes["gen_ai.usage.cache_write_1h_input_tokens"] == 60
    assert model_span.attributes["gen_ai.usage.cost"] == "0.00195"
    assert run_span.attributes["gen_ai.usage.total_cost"] == "0.00195"
    assert run_span.attributes["agent.run.outcome"] == "completed"
    serialized = repr(tuple(record.attributes for record in telemetry.records))
    assert "raw secret" not in serialized


async def test_agent_runner_events_record_cost_and_run_span() -> None:
    """The neutral event surface has the same cost and telemetry semantics."""
    model = ScriptedRoundModel(
        (
            (
                _done(
                    usage=ModelUsage(
                        input_tokens=1_000,
                        output_tokens=0,
                        total_tokens=1_000,
                    )
                ),
            ),
        )
    )
    telemetry = RecordingTelemetry()
    runner = (
        AgentRunner.for_agent_instance(StatelessProbeAgent(model))
        .with_pricing(_pricing())
        .with_telemetry(telemetry)
    )

    events = [
        event
        async for event in runner.run_events(
            RunAgentInput(state_id="priced-events", instruction="answer")
        )
    ]

    terminal = events[-1]
    assert isinstance(terminal, runner_module.RunFinishedEvent)
    assert terminal.metadata["total_cost"] == "0.001"
    assert telemetry.records[-1].kind is AgentSpanKind.RUN
    assert telemetry.records[-1].attributes["agent.run.outcome"] == "completed"


async def test_agent_runner_cost_limit_requires_pricing_before_model_call() -> None:
    """A declared budget without an operator catalog fails before provider usage."""
    model = ScriptedRoundModel(((_done(),),))

    items = await _collect(
        AgentRunner.for_agent_instance(CostLimitedAgent(model)).run(
            RunAgentInput(state_id="missing-pricing", instruction="answer")
        )
    )

    error = cast(Error, items[-1].payload)
    assert error.code == "agent_cost_unavailable"
    assert model.requests == []


@pytest.mark.parametrize(
    ("event", "expected_code"),
    [
        (
            _done(
                usage=ModelUsage(input_tokens=1, output_tokens=1),
                model_ref=None,
            ),
            "agent_cost_unavailable",
        ),
        (_done(usage=ModelUsage()), "agent_cost_unavailable"),
        (
            _done(
                usage=ModelUsage(
                    input_tokens=1_000,
                    output_tokens=1,
                    total_tokens=1_001,
                )
            ),
            "agent_max_cost_exceeded",
        ),
    ],
)
async def test_agent_runner_cost_failures_stop_before_final(
    event: ModelStreamEvent,
    expected_code: str,
) -> None:
    """Missing route/usage and budget overshoot are typed terminal failures."""
    runner = AgentRunner.for_agent_instance(
        CostLimitedAgent(ScriptedRoundModel(((event,),)))
    ).with_pricing(_pricing())

    items = await _collect(
        runner.run(RunAgentInput(state_id=expected_code, instruction="answer"))
    )

    error = cast(Error, items[-1].payload)
    assert error.code == expected_code
    assert not any(item.kind is AgentYieldKind.FINAL for item in items)


def test_agent_runner_cost_initializes_defensive_context_total() -> None:
    """Directly restored execution state cannot lose an otherwise valid step cost."""
    runner = AgentRunner.for_agent_instance(
        StatelessProbeAgent(ScriptedRoundModel(()))
    ).with_pricing(_pricing())
    context = runner_module._ExecutionContext(
        state_id="defensive-cost",
        history=[],
        route_metadata={"model_ref": "model/logical"},
    )

    error = runner._record_cost(
        context,
        ModelUsage(input_tokens=1, output_tokens=1),
    )

    assert error is None
    assert context.total_cost == Decimal("0.000003")


async def test_agent_runner_cost_checkpoint_resumes_without_double_charging() -> None:
    """A paused tool batch restores its bound pricing and cumulative exact cost."""
    state_id = "priced-resume"
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                _done(
                    usage=ModelUsage(
                        input_tokens=1_000,
                        output_tokens=0,
                        total_tokens=1_000,
                    )
                ),
            ),
            (
                _done(
                    usage=ModelUsage(
                        input_tokens=1_000,
                        output_tokens=0,
                        total_tokens=1_000,
                    )
                ),
            ),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    target = ProbeAgent(model, states, signals, FakeEvidenceRepository())
    runner = AgentRunner.for_agent_instance(target).with_pricing(_pricing())

    paused = await _collect(
        runner.run(RunAgentInput(state_id=state_id, instruction="write"))
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    checkpoint = states.get(state_id).metadata[
        runner_module.RUNNER_CHECKPOINT_METADATA_KEY
    ]
    assert isinstance(checkpoint, Mapping)
    assert checkpoint["total_cost"] == "0.001"
    assert checkpoint["pricing_fingerprint"] == _pricing().fingerprint
    signals.append(
        AgentSignal(
            id=approval.id,
            agent_state_id=state_id,
            kind=AgentSignalKind.APPROVAL_DECISION,
            payload={"request_id": approval.id, "decision": "approve"},
        )
    )

    resumed = await _collect(
        runner.run(
            RunAgentInput(
                state_id=state_id,
                instruction="write",
                resume=True,
            )
        )
    )

    assert any(isinstance(item.payload, Tool) for item in resumed)
    final = cast(Final[object], resumed[-1].payload)
    assert final.metadata["total_cost"] == "0.002"
    assert len(model.requests) == 2


async def test_agent_runner_rejects_resume_with_changed_pricing() -> None:
    """A pricing change cannot reinterpret the cost of a paused run."""
    state_id = "changed-pricing"
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                _done(
                    usage=ModelUsage(
                        input_tokens=1,
                        output_tokens=0,
                        total_tokens=1,
                    )
                ),
            ),
        )
    )
    states = FakeStateRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(target)
        .with_pricing(_pricing())
        .run(RunAgentInput(state_id=state_id, instruction="write"))
    )

    resumed = await _collect(
        AgentRunner.for_agent_instance(target)
        .with_pricing(_pricing(version="prices-v2"))
        .run(
            RunAgentInput(
                state_id=state_id,
                instruction="write",
                resume=True,
            )
        )
    )

    error = cast(Error, resumed[-1].payload)
    assert error.code == "agent_checkpoint_invalid"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("total_cost", "0"),
        ("pricing_version", "forged-version"),
        ("cost_currency", "EUR"),
    ],
)
async def test_agent_runner_rejects_forged_pricing_checkpoint(
    key: str,
    value: str,
) -> None:
    """Persisted cost, version, and currency are rebound before resume."""
    state_id = f"forged-pricing-{key}"
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                _done(
                    usage=ModelUsage(
                        input_tokens=1_000,
                        output_tokens=0,
                        total_tokens=1_000,
                    )
                ),
            ),
        )
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        evidence,
    )
    runner = AgentRunner.for_agent_instance(target).with_pricing(_pricing())
    await _collect(runner.run(RunAgentInput(state_id=state_id, instruction="write")))
    current = states.get(state_id)
    checkpoint = current.metadata[runner_module.RUNNER_CHECKPOINT_METADATA_KEY]
    assert isinstance(checkpoint, Mapping)
    forged_checkpoint: dict[str, object] = {**checkpoint, key: value}
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                runner_module.RUNNER_CHECKPOINT_METADATA_KEY: cast(
                    JsonObject,
                    forged_checkpoint,
                ),
            },
        )
    )

    resumed = await _collect(
        runner.run(
            RunAgentInput(
                state_id=state_id,
                instruction="write",
                resume=True,
            )
        )
    )

    assert cast(Error, resumed[-1].payload).code == "agent_checkpoint_invalid"


async def test_agent_runner_failed_surface_spans_include_same_actual_cost() -> None:
    """Budget failure telemetry exposes actual spend on both public surfaces."""
    observed: list[Mapping[str, object]] = []
    for surface in ("run", "events"):
        telemetry = RecordingTelemetry()
        runner = (
            AgentRunner.for_agent_instance(
                CostLimitedAgent(
                    ScriptedRoundModel(
                        (
                            (
                                _done(
                                    usage=ModelUsage(
                                        input_tokens=1_001,
                                        output_tokens=0,
                                        total_tokens=1_001,
                                    )
                                ),
                            ),
                        )
                    )
                )
            )
            .with_pricing(_pricing())
            .with_telemetry(telemetry)
        )
        command = RunAgentInput(
            state_id=f"failed-cost-{surface}",
            instruction="answer",
        )
        if surface == "run":
            await _collect(runner.run(command))
        else:
            async for _event in runner.run_events(command):
                pass
        observed.append(telemetry.records[-1].attributes)

    for attributes in observed:
        assert attributes["agent.run.outcome"] == "failed"
        assert attributes["gen_ai.usage.total_cost"] == "0.001001"
        assert attributes["gen_ai.usage.cost_currency"] == "USD"
        assert attributes["gen_ai.usage.pricing_version"] == "prices-v1"


async def test_agent_runner_paused_surface_spans_include_same_actual_cost() -> None:
    """Approval pause telemetry exposes accumulated spend on both surfaces."""
    observed: list[Mapping[str, object]] = []
    for surface in ("run", "events"):
        state_id = f"paused-cost-{surface}"
        telemetry = RecordingTelemetry()
        target = ProbeAgent(
            ScriptedRoundModel(
                (
                    (
                        _tool_event(
                            "echo.write",
                            {"value": "draft"},
                            "write-1",
                        ),
                        _done(
                            usage=ModelUsage(
                                input_tokens=1_000,
                                output_tokens=0,
                                total_tokens=1_000,
                            )
                        ),
                    ),
                )
            ),
            FakeStateRepository(),
            FakeSignalRepository(()),
            FakeEvidenceRepository(),
        )
        runner = (
            AgentRunner.for_agent_instance(target)
            .with_pricing(_pricing())
            .with_telemetry(telemetry)
        )
        command = RunAgentInput(state_id=state_id, instruction="write")
        if surface == "run":
            await _collect(runner.run(command))
        else:
            async for _event in runner.run_events(command):
                pass
        observed.append(telemetry.records[-1].attributes)

    for attributes in observed:
        assert attributes["agent.run.outcome"] == "paused"
        assert attributes["gen_ai.usage.total_cost"] == "0.001"
        assert attributes["gen_ai.usage.cost_currency"] == "USD"
        assert attributes["gen_ai.usage.pricing_version"] == "prices-v1"


async def test_agent_runner_cancelled_surface_spans_include_same_actual_cost() -> None:
    """Cancellation after a priced pause preserves outcome and spend parity."""
    observed: list[Mapping[str, object]] = []
    for surface in ("run", "events"):
        state_id = f"cancelled-cost-{surface}"
        states = FakeStateRepository()
        signals = FakeSignalRepository(())
        target = ProbeAgent(
            ScriptedRoundModel(
                (
                    (
                        _tool_event(
                            "echo.write",
                            {"value": "draft"},
                            "write-1",
                        ),
                        _done(
                            usage=ModelUsage(
                                input_tokens=1_000,
                                output_tokens=0,
                                total_tokens=1_000,
                            )
                        ),
                    ),
                )
            ),
            states,
            signals,
            FakeEvidenceRepository(),
        )
        await _collect(
            AgentRunner.for_agent_instance(target)
            .with_pricing(_pricing())
            .run(RunAgentInput(state_id=state_id, instruction="write"))
        )
        signals.append(
            AgentSignal(
                id=f"cancel:{surface}",
                agent_state_id=state_id,
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop"},
            )
        )
        telemetry = RecordingTelemetry()
        runner = (
            AgentRunner.for_agent_instance(target)
            .with_pricing(_pricing())
            .with_telemetry(telemetry)
        )
        command = RunAgentInput(
            state_id=state_id,
            instruction="write",
            resume=True,
        )
        if surface == "run":
            await _collect(runner.run(command))
        else:
            async for _event in runner.run_events(command):
                pass
        observed.append(telemetry.records[-1].attributes)

    for attributes in observed:
        assert attributes["agent.run.outcome"] == "cancelled"
        assert attributes["gen_ai.usage.total_cost"] == "0.001"
        assert attributes["gen_ai.usage.cost_currency"] == "USD"
        assert attributes["gen_ai.usage.pricing_version"] == "prices-v1"


@pytest.mark.parametrize(
    "pricing_fields",
    [
        {"pricing_fingerprint": 1},
        {"total_cost": 1},
        {"total_cost": "not-decimal"},
        {"total_cost": "-1"},
        {"total_cost": "NaN"},
        {"pricing_fingerprint": "fingerprint"},
    ],
)
async def test_agent_runner_rejects_malformed_pricing_checkpoint(
    pricing_fields: dict[str, object],
) -> None:
    """Every persisted pricing field is validated before resumed execution."""
    checkpoint: dict[str, object] = {
        "history": [{"role": "user", "content": "x", "metadata": {}}],
        "assistant_text": [],
        "tool_calls": [],
        "step_count": 0,
        "tool_call_count": 0,
        "total_tokens": 0,
        "seen_call_ids": [],
        "approved_call_fingerprints": [],
        "pending_calls": [],
        "route_metadata": {},
        **pricing_fields,
    }
    state_id = f"bad-pricing-{repr(pricing_fields)}"
    states = FakeStateRepository()
    states.save(
        AgentState(
            id=state_id,
            agent_type="runner_probe",
            status=AgentStatus.ACTIVE,
            transition=AgentStateTransition.RUNNING,
            metadata={
                runner_module.RUNNER_CHECKPOINT_METADATA_KEY: cast(
                    JsonObject,
                    checkpoint,
                )
            },
        )
    )
    target = ProbeAgent(
        ScriptedRoundModel(()),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id=state_id, instruction="resume", resume=True)
        )
    )

    assert cast(Error, items[-1].payload).code == "agent_checkpoint_invalid"


async def test_agent_runner_records_function_tool_success_and_failure() -> None:
    """Tool spans expose identity and status without arguments or results."""
    success_telemetry = RecordingTelemetry()
    success_model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "raw secret argument"}, "read-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    await _collect(
        AgentRunner.for_agent_instance(StatelessProbeAgent(success_model))
        .with_telemetry(success_telemetry)
        .run(RunAgentInput(state_id="tool-success", instruction="secret prompt"))
    )
    tool_span = next(
        record
        for record in success_telemetry.records
        if record.kind is AgentSpanKind.TOOL
    )
    assert tool_span.status is AgentSpanStatus.OK
    assert tool_span.attributes["agent.tool.name"] == "echo.read"
    assert tool_span.attributes["agent.tool.kind"] == "function"
    assert "raw secret" not in repr(tool_span.attributes)

    failure_telemetry = RecordingTelemetry()
    states = FakeStateRepository()
    failure_target = FrameworkFailingToolProbeAgent(
        ScriptedRoundModel(
            (
                (
                    _tool_event("framework.raise", {}, "raise-1"),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        ),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(failure_target)
        .with_telemetry(failure_telemetry)
        .run(RunAgentInput(state_id="tool-failure", instruction="fail"))
    )
    failed_tool_span = next(
        record
        for record in failure_telemetry.records
        if record.kind is AgentSpanKind.TOOL
    )
    assert failed_tool_span.status is AgentSpanStatus.ERROR
    assert failed_tool_span.error_code == "agent_tool_execution_failed"


async def test_agent_runner_records_classic_retrieval_span() -> None:
    """Classic RAG retrieval is a distinct span with no query or hit body."""
    retriever = StaticRetriever(
        (
            RetrievalHit(
                id="hit-1",
                content="raw secret retrieved content",
                source="kb:1",
                tenant_id="tenant-1",
                namespace="support",
            ),
        )
    )
    provider = RetrievalContext(
        retriever,
        tenant_id="tenant-1",
        namespace="support",
    )
    telemetry = RecordingTelemetry()
    target = ContextProbeAgent(
        ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),)),
        provider,
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    await _collect(
        AgentRunner.for_agent_instance(target)
        .with_telemetry(telemetry)
        .run(RunAgentInput(state_id="retrieval-span", instruction="raw query"))
    )

    retrieval_span = next(
        record for record in telemetry.records if record.kind is AgentSpanKind.RETRIEVAL
    )
    assert retrieval_span.status is AgentSpanStatus.OK
    assert retrieval_span.attributes["retrieval.hits"] == 1
    assert retrieval_span.attributes["retrieval.limit"] == 5
    assert "raw secret" not in repr(retrieval_span.attributes)
    assert "raw query" not in repr(retrieval_span.attributes)


async def test_agent_runner_records_model_error_span() -> None:
    """A typed provider failure produces error model and run spans."""
    telemetry = RecordingTelemetry()
    runner = AgentRunner.for_agent_instance(
        StatelessProbeAgent(FrameworkFailingModel())
    ).with_telemetry(telemetry)

    items = await _collect(
        runner.run(RunAgentInput(state_id="model-error-span", instruction="fail"))
    )

    assert isinstance(items[-1].payload, Error)
    assert telemetry.records[0].kind is AgentSpanKind.MODEL
    assert telemetry.records[0].status is AgentSpanStatus.ERROR
    assert telemetry.records[-1].kind is AgentSpanKind.RUN
    assert telemetry.records[-1].status is AgentSpanStatus.ERROR


async def test_agent_runner_keeps_nested_resilience_evidence_out_of_span_attributes() -> (
    None
):
    """Attempt details stay durable while telemetry receives scalar summaries only."""
    metadata: JsonObject = {
        "model_ref": "fallback/model",
        "profile": "fallback-profile",
        "provider": "openai",
        "model": "physical-model",
        "attempted_model_ref": "fallback/model",
        "attempted_profile": "fallback-profile",
        "attempted_provider": "openai",
        "attempt_ordinal": 2,
        "attempts": (
            {"model_ref": "primary/model", "failure_class": "timeout"},
            {"model_ref": "fallback/model", "state": "success"},
        ),
        "fallback_used": True,
        "fallback_from": "primary/model",
        "retry_count": 1,
        "circuit_state": "closed",
        "cache_state": "miss",
        "cache_mode": "exact",
        "cache_selections": ({"state": "miss"},),
        "cache_saved_input_tokens": 10,
        "cache_saved_output_tokens": 2,
        "cache_saved_total_tokens": 12,
    }
    telemetry = RecordingTelemetry()
    evidence = FakeEvidenceRepository()
    target = ProbeAgent(
        ScriptedRoundModel(
            (
                (
                    ModelStreamEvent(
                        kind=ModelStreamEventKind.DONE,
                        metadata=metadata,
                    ),
                ),
            )
        ),
        FakeStateRepository(),
        FakeSignalRepository(()),
        evidence,
    )

    await _collect(
        AgentRunner.for_agent_instance(target)
        .with_telemetry(telemetry)
        .run(RunAgentInput(state_id="resilience-evidence", instruction="answer"))
    )

    model_span = next(
        record for record in telemetry.records if record.kind is AgentSpanKind.MODEL
    )
    assert model_span.attributes["fallback_used"] is True
    assert model_span.attributes["retry_count"] == 1
    assert model_span.attributes["cache_state"] == "miss"
    assert model_span.attributes["cache_saved_total_tokens"] == 12
    assert "attempts" not in model_span.attributes
    assert "cache_selections" not in model_span.attributes
    model_evidence = next(
        item
        for item in evidence.list_by_state("resilience-evidence")
        if item.kind is AgentEvidenceKind.MODEL
    )
    decision = cast(Mapping[str, JsonValue], model_evidence.payload["decision"])
    routing = cast(Mapping[str, JsonValue], decision["routing"])
    assert routing["attempts"] == metadata["attempts"]
    assert routing["cache_selections"] == metadata["cache_selections"]


async def test_agent_runner_telemetry_failure_is_typed() -> None:
    """Observer failure never becomes an untyped backend exception."""
    runner = AgentRunner.for_agent_instance(
        StatelessProbeAgent(
            ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))
        )
    ).with_telemetry(RecordingTelemetry(fail=True))

    with pytest.raises(AgentTelemetryError):
        await _collect(
            runner.run(RunAgentInput(state_id="telemetry-failure", instruction="run"))
        )


async def test_agent_runner_events_record_unhandled_exception_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected event-surface failures still close the run span as an error."""

    async def fail_execution_context(
        self: AgentRunner,
        run_input: RunAgentInput,
        state: AgentState | None,
    ) -> runner_module._ExecutionContext:
        raise RuntimeError("unexpected event failure")

    monkeypatch.setattr(AgentRunner, "_execution_context", fail_execution_context)
    telemetry = RecordingTelemetry()
    runner = AgentRunner.for_agent_instance(
        StatelessProbeAgent(ScriptedRoundModel(()))
    ).with_telemetry(telemetry)

    with pytest.raises(RuntimeError, match="unexpected event failure"):
        async for _event in runner.run_events(
            RunAgentInput(state_id="events-exception", instruction="run")
        ):
            pass

    assert telemetry.records[-1].kind is AgentSpanKind.RUN
    assert telemetry.records[-1].status is AgentSpanStatus.ERROR
    assert telemetry.records[-1].error_code == "agent_run_exception"


async def test_agent_runner_rejects_mismatched_final_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public yield discriminator cannot disagree with its payload type."""

    async def invalid_final(
        self: AgentRunner,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Error(code="invalid", message="not a final"),
        )

    monkeypatch.setattr(AgentRunner, "_run_stateless", invalid_final)
    runner = AgentRunner.for_agent_instance(StatelessProbeAgent(ScriptedRoundModel(())))

    with pytest.raises(AgentDefinitionError, match="invalid payload"):
        await _collect(
            runner.run(RunAgentInput(state_id="invalid-final", instruction="run"))
        )


async def test_agent_runner_rejects_mismatched_approval_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval discriminators also fail closed before telemetry accounting."""

    async def invalid_approval(
        self: AgentRunner,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(
            kind=AgentYieldKind.APPROVAL,
            payload=Error(code="invalid", message="not an approval"),
        )

    monkeypatch.setattr(AgentRunner, "_run_stateless", invalid_approval)
    runner = AgentRunner.for_agent_instance(StatelessProbeAgent(ScriptedRoundModel(())))

    with pytest.raises(AgentDefinitionError, match="approval yield"):
        await _collect(
            runner.run(RunAgentInput(state_id="invalid-approval", instruction="run"))
        )


async def test_agent_runner_rejects_mismatched_cancel_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel discriminators cannot hide a non-cancellation payload."""

    async def invalid_cancel(
        self: AgentRunner,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(
            kind=AgentYieldKind.CANCEL,
            payload=Error(code="invalid", message="not a cancel"),
        )

    monkeypatch.setattr(AgentRunner, "_run_stateless", invalid_cancel)
    runner = AgentRunner.for_agent_instance(StatelessProbeAgent(ScriptedRoundModel(())))

    with pytest.raises(AgentDefinitionError, match="cancel yield"):
        await _collect(
            runner.run(RunAgentInput(state_id="invalid-cancel", instruction="run"))
        )


@pytest.mark.parametrize(
    "decisions",
    [
        ("invalid",),
        (
            {
                "step": 0,
                "routing": {"model_ref": "model/logical"},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 2,
                "routing": {"model_ref": "model/logical"},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 1,
                "routing": [],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 1,
                "routing": {"model_ref": ""},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 1,
                "routing": {"model_ref": "model/logical"},
                "usage": {"input_tokens": True, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 1,
                "routing": {"model_ref": "unknown"},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (
            {
                "step": 1,
                "routing": {"model_ref": "model/logical"},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            {
                "step": 1,
                "routing": {"model_ref": "model/logical"},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ),
        (),
    ],
)
def test_agent_runner_rejects_untrusted_model_cost_evidence(
    decisions: tuple[object, ...],
) -> None:
    """Resume cost reconstruction validates every append-only model receipt."""
    state_id = "bad-cost-evidence"
    evidence = FakeEvidenceRepository()
    for index, decision in enumerate(decisions, start=1):
        evidence.append(
            AgentEvidence(
                id=f"evidence-{index}",
                agent_state_id=state_id,
                kind=AgentEvidenceKind.MODEL,
                payload=cast(
                    JsonObject,
                    {"model": "model", "decision": decision},
                ),
            )
        )
    runner = AgentRunner.for_agent_instance(
        ProbeAgent(
            ScriptedRoundModel(()),
            FakeStateRepository(),
            FakeSignalRepository(()),
            evidence,
        )
    ).with_pricing(_pricing())
    context = runner_module._ExecutionContext(
        state_id=state_id,
        history=[],
        step_count=1,
        total_cost=Decimal("0.000003"),
        pricing_version="prices-v1",
        cost_currency="USD",
    )

    with pytest.raises(AgentDefinitionError):
        runner._validate_restored_pricing(state_id, context)


def test_agent_runner_rejects_pricing_catalog_and_total_mismatch() -> None:
    """Catalog identity and recomputed total are independently enforced on resume."""
    state_id = "pricing-cross-check"
    evidence = FakeEvidenceRepository()
    evidence.append(
        AgentEvidence(
            id="model-1",
            agent_state_id=state_id,
            kind=AgentEvidenceKind.MODEL,
            payload={
                "model": "physical",
                "decision": {
                    "step": 1,
                    "routing": {"model_ref": "model/logical"},
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        )
    )
    runner = AgentRunner.for_agent_instance(
        ProbeAgent(
            ScriptedRoundModel(()),
            FakeStateRepository(),
            FakeSignalRepository(()),
            evidence,
        )
    ).with_pricing(_pricing())
    wrong_catalog = runner_module._ExecutionContext(
        state_id=state_id,
        history=[],
        step_count=1,
        total_cost=Decimal("0.000003"),
        pricing_version="wrong",
        cost_currency="USD",
    )
    wrong_total = replace(
        wrong_catalog,
        total_cost=Decimal("0.000004"),
        pricing_version="prices-v1",
    )

    with pytest.raises(AgentDefinitionError, match="catalog"):
        runner._validate_restored_pricing(state_id, wrong_catalog)
    with pytest.raises(AgentDefinitionError, match="does not match"):
        runner._validate_restored_pricing(state_id, wrong_total)


def test_runner_observability_helpers_filter_untyped_cost_metadata() -> None:
    """Only typed scalar cost fields can enter telemetry attributes."""
    assert (
        runner_module._cost_metadata(
            runner_module._ExecutionContext(state_id="no-cost", history=[])
        )
        == {}
    )
    assert (
        runner_module._telemetry_cost_attributes(
            {
                "total_cost": 1,
                "cost_currency": None,
                "pricing_version": [],
            }
        )
        == {}
    )
