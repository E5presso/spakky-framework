"""Tests for the framework-owned AgentRunner execution loop."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import override

import pytest
from pydantic import BaseModel

from spakky.agent import (
    Agent,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentRunner,
    AgentRunResult,
    AgentSignalKind,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Approval,
    Cancel,
    Error,
    EvidenceCapture,
    Final,
    IAgentModel,
    Idempotency,
    JsonValue,
    ModelCapability,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    Progress,
    RecoveryStrategy,
    Token,
    Tool,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.error import (
    AgentModelConfigurationError,
    AgentPersistenceConfigurationError,
    AgentToolDispatchError,
)
from spakky.agent.inbound import RunAgentInput
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingModel,
)

DURABLE_SPEC = AgentExecutionSpec(
    name="runner_probe",
    accepted_signals=(
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
        AgentSignalKind.RESUME,
    ),
    recovery=RecoveryStrategy.ACTION_BOUNDARY,
)


class EchoResult(BaseModel):
    """Pydantic tool result used to prove neutral serialization."""

    value: str


@dataclass(frozen=True, slots=True)
class EchoRecord:
    """Dataclass tool result used to prove neutral serialization."""

    value: str


@Agent(spec=DURABLE_SPEC)
class ProbeAgent:
    """Durable probe agent exercising the framework-owned loop end to end."""

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

    @agent_tool(
        schema_name="echo.read",
        description="Read echo without approval.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo_read(self, value: str) -> EchoRecord:
        """Echo a value back as a structured result."""
        return EchoRecord(value=value)

    @agent_tool(
        schema_name="echo.write",
        description="Write echo requiring approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def echo_write(self, value: str) -> EchoRecord:
        """Echo a value back after approval."""
        return EchoRecord(value=value)


@Agent(spec=AgentExecutionSpec(name="stateless_probe"))
class StatelessProbeAgent:
    """Stateless probe agent that runs model to final without durability."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="echo.read",
        description="Read echo without approval.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo_read(self, value: str) -> EchoRecord:
        """Echo a value back as a structured result."""
        return EchoRecord(value=value)


@Agent(spec=AgentExecutionSpec(name="toolless_probe"))
class ToollessProbeAgent:
    """Stateless agent with no tools to prove tool_calling stays absent."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


def _invoke_execute(
    agent: object,
    run_input: RunAgentInput,
) -> AsyncIterator[AgentYield[object]]:
    """Invoke an agent's framework-provided execute() without static binding.

    The synthesized execute() is bound onto the class at decoration time, so it
    is read from the class namespace (``vars``) rather than as a statically known
    attribute, then called with the instance as the bound ``self``.
    """
    execute = vars(type(agent))["execute"]
    return execute(agent, run_input)


async def _collect(
    stream: AsyncIterator[AgentYield[object]],
) -> tuple[AgentYield[object], ...]:
    items: list[AgentYield[object]] = []
    async for item in stream:
        items.append(item)
    return tuple(items)


async def _run_durable(
    model: IAgentModel,
    command: RunAgentInput,
    states: FakeStateRepository,
    signals: FakeSignalRepository,
    evidence: FakeEvidenceRepository,
) -> tuple[AgentYield[object], ...]:
    agent = ProbeAgent(model, states, signals, evidence)
    return await _collect(_invoke_execute(agent, command))


def _tool_event(
    name: str, arguments: dict[str, JsonValue], call_id: str
) -> ModelStreamEvent:
    return ModelStreamEvent(
        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        tool_call=ModelToolCall(name=name, arguments=arguments, call_id=call_id),
    )


def _approval_signal(state_id: str, request_id: str, decision: str):
    from spakky.agent import AgentSignal

    return AgentSignal(
        id=request_id,
        agent_state_id=state_id,
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"request_id": request_id, "decision": decision},
    )


async def test_agent_runner_expect_auto_provided_execute_runs_tools_and_final() -> None:
    """spec과 @agent_tool만 선언한 Agent가 도구 호출과 종료까지 자동 실행된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="planning",
            ),
            _tool_event("echo.read", {"value": "hi"}, "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="echo"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    kinds = {item.kind for item in items}
    assert {
        AgentYieldKind.TOKEN,
        AgentYieldKind.TOOL,
        AgentYieldKind.EVIDENCE,
        AgentYieldKind.FINAL,
    } <= kinds
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_approval_pause_then_signal_resume_dispatches() -> (
    None
):
    """승인 필요 도구가 pause 후 승인 signal 수신으로 resume되어 디스패치된다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    signals = FakeSignalRepository(
        (_approval_signal("run-1", "approval:run-1:echo.write", "approve"),)
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        evidence,
    )

    assert any(isinstance(item.payload, Approval) for item in items)
    assert any(isinstance(item.payload, Tool) for item in items)
    assert AgentEvidenceKind.APPROVAL in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_approval_skips_unrelated_and_mismatched_signals() -> (
    None
):
    """승인 대기 큐의 무관 signal과 다른 request_id 결정은 건너뛰고 일치 결정만 쓴다."""
    from spakky.agent import AgentSignal

    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="resume:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.RESUME,
                payload={},
            ),
            _approval_signal("run-1", "approval:run-1:other.tool", "approve"),
            _approval_signal("run-1", "approval:run-1:echo.write", "approve"),
        )
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_cancel_without_requested_by_omits_attribution() -> (
    None
):
    """requested_by가 없는 cancel signal은 Cancel.requested_by를 None으로 둔다."""
    from spakky.agent import AgentSignal

    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="cancel"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    cancel = items[0].payload
    assert isinstance(cancel, Cancel)
    assert cancel.requested_by is None


async def test_agent_runner_expect_approval_reject_stops_without_final() -> None:
    """승인 거부 결정은 도구 디스패치 없이 FINAL 없이 종료한다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (_approval_signal("run-1", "approval:run-1:echo.write", "reject"),)
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert not any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.FAILED


async def test_agent_runner_expect_no_pending_decision_pauses_without_dispatch() -> (
    None
):
    """승인 결정 signal이 없으면 paused 상태에서 도구를 디스패치하지 않는다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Approval) for item in items)
    assert not any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.INTERRUPTED


async def test_agent_runner_expect_model_error_fails_state_and_yields_error() -> None:
    """모델 ERROR 이벤트는 상태를 FAILED로 두고 Error를 노출하며 종료한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(
                    code="rate_limited",
                    message="provider rate limit",
                    retryable=True,
                ),
            ),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="boom"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "rate_limited"
    assert states.get("run-1").status is AgentStatus.FAILED


async def test_agent_runner_expect_cancel_signal_pre_loop_terminates() -> None:
    """모델 루프 전 CANCEL signal은 CANCELLED와 cancellation evidence로 끝난다."""
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()

    from spakky.agent import AgentSignal

    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop", "requested_by": "tester"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="cancel"),
        states,
        signals,
        evidence,
    )

    assert len(items) == 1
    assert isinstance(items[0].payload, Cancel)
    assert states.get("run-1").status is AgentStatus.CANCELLED
    assert AgentEvidenceKind.CANCELLATION in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }


async def test_agent_runner_expect_cancel_signal_mid_stream_terminates() -> None:
    """스트림 진행 중 도착한 CANCEL signal도 즉시 종료시킨다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    model = _CancelInjectingModel(states, signals)

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="cancel mid"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Cancel) for item in items)
    assert states.get("run-1").status is AgentStatus.CANCELLED


async def test_agent_runner_expect_user_message_signal_consumed_as_progress() -> None:
    """USER_MESSAGE signal은 progress와 evaluation evidence로 소비된다."""
    from spakky.agent import AgentSignal

    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="user:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "keep it small"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="ok"
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        RunAgentInput(state_id="run-1", instruction="hello"),
        states,
        signals,
        evidence,
    )

    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and item.payload.current_step == "signal"
        for item in items
    )
    assert AgentEvidenceKind.EVALUATION in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }


async def test_agent_runner_expect_resume_emits_skip_completed_progress() -> None:
    """resume 입력은 persisted boundary로 skip_completed resume 계획을 노출한다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()

    await _run_durable(
        RecordingModel(
            (
                _tool_event("echo.read", {"value": "x"}, "read-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        RunAgentInput(state_id="resume-run", instruction="first"),
        states,
        signals,
        evidence,
    )
    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="resume-run", instruction="again", resume=True),
        states,
        signals,
        evidence,
    )

    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and "skip_completed" in item.payload.message
        for item in items
    )


async def test_agent_runner_expect_reasoning_suppressed_when_capability_absent() -> (
    None
):
    """capability가 reasoning을 지원하지 않으면 reasoning delta는 생략된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="reason"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(item.payload, Token) for item in items)


async def test_agent_runner_expect_reasoning_surfaced_when_capability_present() -> None:
    """capability가 reasoning을 지원하면 reasoning delta가 token으로 노출된다."""
    model = _ReasoningModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="reason"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(
        isinstance(item.payload, Token) and item.payload.text == "thinking"
        for item in items
    )


async def test_agent_runner_expect_message_delta_surfaced_as_token() -> None:
    """MESSAGE_DELTA는 assistant 텍스트로서 token으로 노출된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="hello",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="say hi"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(
        isinstance(item.payload, Token) and item.payload.text == "hello"
        for item in items
    )


async def test_agent_runner_expect_unknown_event_kind_ignored() -> None:
    """surfacing 대상이 아닌 이벤트 종류는 조용히 무시된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.PROGRESS),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="progress"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_tool_call_without_payload_ignored() -> None:
    """tool_call이 없는 TOOL_CALL_CANDIDATE는 도구 디스패치 없이 무시된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="empty tool"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(item.payload, Tool) for item in items)
    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_empty_catalog_sends_no_tool_calling() -> None:
    """도구가 없는 agent의 모델 요청에는 tool_calling이 비어 있다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    agent = ToollessProbeAgent(model)
    await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert model.requests
    assert model.requests[0].tool_calling is None


async def test_agent_runner_expect_stateless_agent_runs_model_to_final() -> None:
    """durable port가 없는 stateless agent도 model→tool→final로 동작한다."""
    model = RecordingModel(
        (
            _tool_event("echo.read", {"value": "hi"}, "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert any(isinstance(item.payload, Tool) for item in items)
    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_stateless_model_error_yields_error_without_final() -> (
    None
):
    """stateless agent의 모델 ERROR도 FINAL 없이 Error를 노출하며 종료한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(code="boom", message="stateless failure"),
            ),
        )
    )

    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "boom"


async def test_agent_runner_expect_missing_model_raises_configuration_error() -> None:
    """IAgentModel 포트가 주입되지 않으면 model configuration error로 실패한다."""

    @Agent(spec=AgentExecutionSpec(name="no_model"))
    class NoModelAgent:
        def __init__(self) -> None:
            self._note = "no model"

    agent = NoModelAgent()
    with pytest.raises(AgentModelConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_two_models_injected_raises() -> None:
    """동일 포트가 둘 이상 주입되면 모호하므로 configuration error로 실패한다."""
    model = RecordingModel(())

    @Agent(spec=AgentExecutionSpec(name="two_models"))
    class TwoModelAgent:
        def __init__(self, primary: IAgentModel, secondary: IAgentModel) -> None:
            self._primary = primary
            self._secondary = secondary

    agent = TwoModelAgent(model, RecordingModel(()))
    with pytest.raises(AgentModelConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_durable_agent_missing_repository_raises() -> None:
    """durable spec인데 repository 포트가 빠지면 persistence error로 실패한다."""
    model = RecordingModel(())

    @Agent(spec=DURABLE_SPEC, name="durable_partial")
    class DurablePartialAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    agent = DurablePartialAgent(model)
    with pytest.raises(AgentPersistenceConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_dataclass_tool_result_serialized() -> None:
    """dataclass 도구 결과는 JSON 호환 매핑으로 직렬화된다."""
    result = _serialize_tool_result(EchoRecord(value="rec"))

    assert result == {"value": "rec"}


async def test_agent_runner_expect_basemodel_tool_result_serialized() -> None:
    """pydantic BaseModel 도구 결과는 model_dump로 직렬화된다."""
    result = _serialize_tool_result(EchoResult(value="model"))

    assert result == {"value": "model"}


async def test_agent_runner_expect_sequence_tool_result_serialized() -> None:
    """시퀀스 도구 결과는 JSON 호환 리스트로 직렬화된다."""
    result = _serialize_tool_result([EchoRecord(value="a"), {"k": 1}])

    assert result == [{"value": "a"}, {"k": 1}]


async def test_agent_runner_expect_scalar_tool_result_passthrough() -> None:
    """스칼라 도구 결과는 그대로 통과한다."""
    assert _serialize_tool_result(7) == 7


async def test_agent_runner_expect_unknown_tool_result_type_raises() -> None:
    """직렬화 불가능한 도구 결과는 dispatch error로 거부된다."""
    with pytest.raises(AgentToolDispatchError):
        _serialize_tool_result(object())


async def test_agent_runner_expect_nested_unknown_value_raises() -> None:
    """매핑 내부의 직렬화 불가 값도 dispatch error로 거부된다."""
    with pytest.raises(AgentToolDispatchError):
        _serialize_tool_result({"bad": object()})


async def test_agent_runner_expect_output_type_recorded_in_final_metadata() -> None:
    """spec.output_type가 선언되면 final metadata에 그 이름이 기록된다."""

    @Agent(spec=AgentExecutionSpec(name="typed_output", output_type=EchoResult))
    class TypedOutputAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    agent = TypedOutputAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    final = items[-1].payload
    assert isinstance(final, Final)
    assert isinstance(final.output, AgentRunResult)
    assert final.metadata["output_type"] == "EchoResult"


async def test_agent_runner_expect_default_output_type_metadata_none() -> None:
    """output_type 미선언이면 final metadata의 output_type은 None이다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    final = items[-1].payload
    assert isinstance(final, Final)
    assert final.metadata["output_type"] is None


def _serialize_tool_result(result: object) -> JsonValue:
    from spakky.agent.runner import _tool_result_json

    return _tool_result_json(result)


class _ReasoningModel(RecordingModel):
    """RecordingModel variant declaring reasoning capability."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_reasoning=True)


class _CancelInjectingModel(IAgentModel):
    """Model that appends a cancel signal before its first stream event."""

    def __init__(
        self,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
    ) -> None:
        self._states = states
        self._signals = signals

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        from spakky.agent import AgentSignal

        self._signals.append(
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "mid", "requested_by": "tester"},
            )
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="t")
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
