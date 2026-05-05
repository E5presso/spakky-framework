"""Tests for spakky-agent public API exports."""

from collections.abc import AsyncGenerator

import pytest
import spakky.agent as agent_api
import tests.fixtures.agent_app as agent_app
from spakky.agent import (
    IAgentModel,
    AgentApprovalBoundaryKind,
    AgentApprovalDecisionOutcome,
    AgentApprovalPlan,
    AgentApprovalPlanAction,
    AgentApprovalRequest,
    AgentActionBoundaryCheckpoint,
    AgentActionBoundaryStage,
    AgentActionKind,
    AgentCancellationCleanupReport,
    AgentCancellationCleanupResult,
    AgentCancellationCleanupStatus,
    AgentCancellationCleanupTask,
    AgentCancellationRequest,
    AgentCancellationTargetKind,
    AgentToolCatalog,
    AgentToolBindingError,
    AgentToolBoundInvocation,
    AgentToolDescriptor,
    AgentToolIdentity,
    AgentEvidenceCandidate,
    Agent,
    AgentBootstrapError,
    AgentDefinitionError,
    AgentEvidence,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentDelegateTarget,
    AgentPersistenceConfigurationError,
    AgentResumeAction,
    AgentResumeBoundary,
    AgentResumePlan,
    AgentSignal,
    AgentSignalConsumptionBatch,
    AgentSignalKind,
    AgentState,
    AgentStatus,
    AgentYield,
    Cancel,
    ContextDigest,
    ContextHealthSignal,
    ContextManifest,
    ContextOptimizationAction,
    ContextOptimizationActionKind,
    ContextOptimizationEvidenceStage,
    ContextPack,
    ContextRotSymptom,
    Error,
    Final,
    IAgentContextHandler,
    IAgentDelegate,
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
    AgentSignalPollPoint,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelToolCall,
    ModelToolSpec,
    Progress,
    RecoveryStrategy,
    StreamingOptions,
    Token,
    Tool,
    ToolEffects,
    ToolPermission,
    ToolResumeAction,
    ToolResumeMetadata,
    ToolRisk,
    ToolRiskAxis,
    ToolCallingSpec,
    agent_tool,
    begin_agent_cancellation,
    complete_agent_cancellation,
    consume_pending_agent_signals,
    materialize_agent_approval_decision_state,
    parse_agent_approval_decision_signal,
    plan_agent_resume,
    plan_agent_tool_approval,
    run_agent_cancellation_cleanup,
)
from spakky.agent.main import initialize
from spakky.agent.post_processor import AgentBootstrapValidationPostProcessor
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod


def test_public_api_expect_exports_required_agent_surface() -> None:
    """이슈 #213이 요구한 public import surface를 노출하는지 검증한다."""
    required_exports = {
        "Agent",
        "AgentApprovalBoundaryKind",
        "AgentApprovalDecisionOutcome",
        "AgentApprovalPlan",
        "AgentApprovalPlanAction",
        "AgentApprovalRequest",
        "AgentActionBoundaryCheckpoint",
        "AgentActionBoundaryStage",
        "AgentActionKind",
        "AgentCancellationCleanupReport",
        "AgentCancellationCleanupResult",
        "AgentCancellationCleanupStatus",
        "AgentCancellationCleanupTask",
        "AgentCancellationRequest",
        "AgentCancellationTargetKind",
        "AgentDelegateTarget",
        "AgentExecutionLimits",
        "AgentExecutionSpec",
        "AgentYield",
        "Cancel",
        "Error",
        "AgentState",
        "AgentSignal",
        "AgentSignalConsumptionBatch",
        "AgentSignalPollPoint",
        "AgentEvidence",
        "AgentEvidenceCandidate",
        "AgentResumeAction",
        "AgentResumeBoundary",
        "AgentResumePlan",
        "ContextPack",
        "ContextManifest",
        "ContextDigest",
        "ContextHealthSignal",
        "ContextRotSymptom",
        "ContextOptimizationAction",
        "ContextOptimizationActionKind",
        "ContextOptimizationEvidenceStage",
        "IAgentContextHandler",
        "IAgentStateRepository",
        "IAgentSignalRepository",
        "IAgentEvidenceRepository",
        "IAgentDelegate",
        "IAgentModel",
        "Progress",
        "Token",
        "Tool",
        "agent_tool",
        "AgentToolBindingError",
        "AgentToolBoundInvocation",
        "AgentToolCatalog",
        "AgentToolDescriptor",
        "AgentToolIdentity",
        "begin_agent_cancellation",
        "complete_agent_cancellation",
        "consume_pending_agent_signals",
        "materialize_agent_approval_decision_state",
        "parse_agent_approval_decision_signal",
        "plan_agent_resume",
        "plan_agent_tool_approval",
        "run_agent_cancellation_cleanup",
    }

    exported = set(agent_api.__all__)

    assert required_exports <= exported
    assert Agent is agent_api.Agent
    assert AgentApprovalBoundaryKind is agent_api.AgentApprovalBoundaryKind
    assert AgentApprovalDecisionOutcome is agent_api.AgentApprovalDecisionOutcome
    assert AgentApprovalPlan is agent_api.AgentApprovalPlan
    assert AgentApprovalPlanAction is agent_api.AgentApprovalPlanAction
    assert AgentApprovalRequest is agent_api.AgentApprovalRequest
    assert AgentActionBoundaryCheckpoint is agent_api.AgentActionBoundaryCheckpoint
    assert AgentActionBoundaryStage is agent_api.AgentActionBoundaryStage
    assert AgentActionKind is agent_api.AgentActionKind
    assert AgentCancellationCleanupReport is agent_api.AgentCancellationCleanupReport
    assert AgentCancellationCleanupResult is agent_api.AgentCancellationCleanupResult
    assert AgentCancellationCleanupStatus is agent_api.AgentCancellationCleanupStatus
    assert AgentCancellationCleanupTask is agent_api.AgentCancellationCleanupTask
    assert AgentCancellationRequest is agent_api.AgentCancellationRequest
    assert AgentCancellationTargetKind is agent_api.AgentCancellationTargetKind
    assert AgentDelegateTarget is agent_api.AgentDelegateTarget
    assert AgentExecutionLimits is agent_api.AgentExecutionLimits
    assert AgentExecutionSpec is agent_api.AgentExecutionSpec
    assert AgentYield is agent_api.AgentYield
    assert Cancel is agent_api.Cancel
    assert Error is agent_api.Error
    assert AgentState is agent_api.AgentState
    assert AgentSignal is agent_api.AgentSignal
    assert AgentSignalConsumptionBatch is agent_api.AgentSignalConsumptionBatch
    assert AgentSignalPollPoint is agent_api.AgentSignalPollPoint
    assert AgentEvidence is agent_api.AgentEvidence
    assert AgentEvidenceCandidate is agent_api.AgentEvidenceCandidate
    assert AgentResumeAction is agent_api.AgentResumeAction
    assert AgentResumeBoundary is agent_api.AgentResumeBoundary
    assert AgentResumePlan is agent_api.AgentResumePlan
    assert ContextPack is agent_api.ContextPack
    assert ContextManifest is agent_api.ContextManifest
    assert ContextDigest is agent_api.ContextDigest
    assert ContextHealthSignal is agent_api.ContextHealthSignal
    assert ContextRotSymptom is agent_api.ContextRotSymptom
    assert ContextOptimizationAction is agent_api.ContextOptimizationAction
    assert ContextOptimizationActionKind is agent_api.ContextOptimizationActionKind
    assert (
        ContextOptimizationEvidenceStage is agent_api.ContextOptimizationEvidenceStage
    )
    assert IAgentContextHandler is agent_api.IAgentContextHandler
    assert IAgentStateRepository is agent_api.IAgentStateRepository
    assert IAgentSignalRepository is agent_api.IAgentSignalRepository
    assert IAgentEvidenceRepository is agent_api.IAgentEvidenceRepository
    assert IAgentDelegate is agent_api.IAgentDelegate
    assert IAgentModel is agent_api.IAgentModel
    assert Progress is agent_api.Progress
    assert Token is agent_api.Token
    assert Tool is agent_api.Tool
    assert agent_tool is agent_api.agent_tool
    assert AgentToolBindingError is agent_api.AgentToolBindingError
    assert AgentToolBoundInvocation is agent_api.AgentToolBoundInvocation
    assert AgentToolCatalog is agent_api.AgentToolCatalog
    assert AgentToolDescriptor is agent_api.AgentToolDescriptor
    assert AgentToolIdentity is agent_api.AgentToolIdentity
    assert begin_agent_cancellation is agent_api.begin_agent_cancellation
    assert complete_agent_cancellation is agent_api.complete_agent_cancellation
    assert consume_pending_agent_signals is agent_api.consume_pending_agent_signals
    assert (
        materialize_agent_approval_decision_state
        is agent_api.materialize_agent_approval_decision_state
    )
    assert (
        parse_agent_approval_decision_signal
        is agent_api.parse_agent_approval_decision_signal
    )
    assert plan_agent_resume is agent_api.plan_agent_resume
    assert plan_agent_tool_approval is agent_api.plan_agent_tool_approval
    assert run_agent_cancellation_cleanup is agent_api.run_agent_cancellation_cleanup


def test_public_api_expect_exports_model_contract_types() -> None:
    """IAgentModel이 사용하는 provider-neutral request/response 타입을 노출한다."""
    assert ModelRequest is agent_api.ModelRequest
    assert ModelResponse is agent_api.ModelResponse
    assert ModelStreamEvent is agent_api.ModelStreamEvent
    assert ModelToolSpec is agent_api.ModelToolSpec
    assert ToolCallingSpec is agent_api.ToolCallingSpec
    assert ModelToolCall is agent_api.ModelToolCall
    assert ModelError is agent_api.ModelError
    assert StreamingOptions is agent_api.StreamingOptions


def test_public_api_expect_exports_tool_metadata_types() -> None:
    """@agent_tool descriptor metadata 타입을 public API로 노출한다."""
    assert ToolPermission is agent_api.ToolPermission
    assert ToolEffects is agent_api.ToolEffects
    assert ToolRisk is agent_api.ToolRisk
    assert ToolRiskAxis is agent_api.ToolRiskAxis
    assert ToolResumeAction is agent_api.ToolResumeAction
    assert ToolResumeMetadata is agent_api.ToolResumeMetadata


def test_public_api_expect_exports_custom_error_hierarchy() -> None:
    """bootstrap/definition 오류가 custom error 계층으로 표현되는지 검증한다."""
    assert issubclass(AgentDefinitionError, agent_api.AbstractSpakkyAgentError)
    assert issubclass(AgentBootstrapError, agent_api.AbstractSpakkyAgentError)


def test_initialize_expect_registers_only_bootstrap_validation() -> None:
    """core package 초기화가 persistence/model fallback 없이 검증기만 등록한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(AgentBootstrapValidationPostProcessor) is True
    assert app.container.contains(IAgentModel) is False


async def test_agent_expect_scans_resolves_and_invokes_like_usecase() -> None:
    """@Agent class가 scan, constructor DI, 직접 execute 호출에 참여한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)

    app.scan(agent_app).start()

    agent = app.container.get(agent_app.CodeAssistant)
    items: list[AgentYield[Final[str]]] = []
    async for item in agent.execute("ticket-214"):
        items.append(item)

    assert len(items) == 1
    assert items[0].payload.output == "handled:ticket-214"


def test_agent_bootstrap_expect_surfaces_execute_contract_as_custom_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap 재검증에서 execute 계약 손상이 custom error로 드러난다."""

    @Agent()
    class ValidAtDefinition:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=agent_api.AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    agent = Agent.get(ValidAtDefinition)
    monkeypatch.setattr(agent.target, "execute", _invalid_execute)

    with pytest.raises(AgentBootstrapError):
        AgentBootstrapValidationPostProcessor().post_process(ValidAtDefinition())


async def _invalid_execute(command: str) -> AsyncGenerator[str, None]:
    yield command


def test_agent_bootstrap_expect_durable_agent_requires_persistence_contribution() -> (
    None
):
    """durable 실행 경로가 repository contribution 없이 시작되지 않음을 검증한다."""

    @Agent(spec=AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY))
    class DurableAgentWithoutPersistence:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=agent_api.AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(DurableAgentWithoutPersistence)

    with pytest.raises(AgentPersistenceConfigurationError) as exc_info:
        app.start()

    message = str(exc_info.value)
    assert "DurableAgentWithoutPersistence" in message
    assert "IAgentStateRepository" in message
    assert "IAgentSignalRepository" in message
    assert "IAgentEvidenceRepository" in message
    assert "spakky-sqlalchemy[agent]" in message
    assert "spakky.contributions.spakky.agent" in message


def test_agent_bootstrap_expect_manual_processor_requires_injected_container() -> None:
    """수동 post processor 호출도 durable fallback 없이 custom error를 낸다."""

    @Agent(spec=AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY))
    class DurableAgentWithoutContainer:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=agent_api.AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    with pytest.raises(AgentPersistenceConfigurationError):
        AgentBootstrapValidationPostProcessor().post_process(
            DurableAgentWithoutContainer()
        )


def test_agent_bootstrap_expect_signal_acceptance_requires_persistence_contribution() -> (
    None
):
    """signal을 받는 agent가 durable inbound queue contribution을 요구한다."""

    @Agent(spec=AgentExecutionSpec(accepted_signals=(AgentSignalKind.USER_MESSAGE,)))
    class SignaledAgentWithoutPersistence:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=agent_api.AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(SignaledAgentWithoutPersistence)

    with pytest.raises(AgentPersistenceConfigurationError):
        app.start()


def test_agent_bootstrap_expect_durable_agent_starts_with_repository_contribution() -> (
    None
):
    """필수 repository port가 등록되면 durable agent bootstrap이 통과한다."""

    @Agent(spec=AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY))
    class DurableAgentWithPersistence:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=agent_api.AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(FakeAgentStateRepository)
    app.add(FakeAgentSignalRepository)
    app.add(FakeAgentEvidenceRepository)
    app.add(DurableAgentWithPersistence)

    app.start()

    app.stop()


def test_agent_bootstrap_type_name_expect_handles_non_class_target() -> None:
    """diagnostic helper가 비정상 target도 문자열로 표현한다."""

    agent = Agent()
    agent.target = _invalid_execute

    name = AgentBootstrapValidationPostProcessor()._agent_type_name(agent)

    assert name == str(_invalid_execute)


class FakeRepositoryAccessError(Exception):
    """Raised when a repository test double is invoked unexpectedly."""


@Pod()
class FakeAgentStateRepository(IAgentStateRepository):
    """Test-only AgentState repository double."""

    def get(self, state_id: str) -> AgentState:
        raise FakeRepositoryAccessError

    def get_or_none(self, state_id: str) -> AgentState | None:
        raise FakeRepositoryAccessError

    def save(self, state: AgentState) -> AgentState:
        return state

    def list_by_status(self, status: AgentStatus) -> tuple[AgentState, ...]:
        return ()

    def list_resume_candidates(self) -> tuple[AgentState, ...]:
        return ()


@Pod()
class FakeAgentSignalRepository(IAgentSignalRepository):
    """Test-only AgentSignal repository double."""

    def append(self, signal: AgentSignal) -> AgentSignal:
        return signal

    def list_pending(self, state_id: str) -> tuple[AgentSignal, ...]:
        return ()

    def mark_consumed(self, signal_id: str) -> AgentSignal:
        raise FakeRepositoryAccessError


@Pod()
class FakeAgentEvidenceRepository(IAgentEvidenceRepository):
    """Test-only AgentEvidence repository double."""

    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        return evidence

    def get(self, evidence_id: str) -> AgentEvidence:
        raise FakeRepositoryAccessError

    def list_by_state(self, state_id: str) -> tuple[AgentEvidence, ...]:
        return ()

    def list_by_manifest_ref(self, manifest_ref: str) -> tuple[AgentEvidence, ...]:
        return ()
