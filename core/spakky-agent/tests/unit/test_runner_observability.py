"""Acceptance-level tests for Agent cost budgets and privacy-safe telemetry."""

from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import cast, override

import pytest

import spakky.agent.runner as runner_module
from spakky.agent import (
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
    ModelPrice,
    ModelPricingCatalog,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
    RetrievalContext,
    RetrievalHit,
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
