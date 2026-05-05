"""Tests for spakky-agent public API exports."""

from collections.abc import AsyncGenerator

import pytest
import spakky.agent as agent_api
import tests.fixtures.agent_app as agent_app
from spakky.agent import (
    IAgentModel,
    Agent,
    AgentBootstrapError,
    AgentDefinitionError,
    AgentEvidence,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentSignal,
    AgentState,
    AgentYield,
    ContextDigest,
    ContextManifest,
    ContextPack,
    Final,
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelToolCall,
    ModelToolSpec,
    StreamingOptions,
    ToolCallingSpec,
)
from spakky.agent.main import initialize
from spakky.agent.post_processor import AgentBootstrapValidationPostProcessor
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_public_api_expect_exports_required_agent_surface() -> None:
    """이슈 #213이 요구한 public import surface를 노출하는지 검증한다."""
    required_exports = {
        "Agent",
        "AgentExecutionLimits",
        "AgentExecutionSpec",
        "AgentYield",
        "AgentState",
        "AgentSignal",
        "AgentEvidence",
        "ContextPack",
        "ContextManifest",
        "ContextDigest",
        "IAgentStateRepository",
        "IAgentSignalRepository",
        "IAgentEvidenceRepository",
        "IAgentModel",
    }

    exported = set(agent_api.__all__)

    assert required_exports <= exported
    assert Agent is agent_api.Agent
    assert AgentExecutionLimits is agent_api.AgentExecutionLimits
    assert AgentExecutionSpec is agent_api.AgentExecutionSpec
    assert AgentYield is agent_api.AgentYield
    assert AgentState is agent_api.AgentState
    assert AgentSignal is agent_api.AgentSignal
    assert AgentEvidence is agent_api.AgentEvidence
    assert ContextPack is agent_api.ContextPack
    assert ContextManifest is agent_api.ContextManifest
    assert ContextDigest is agent_api.ContextDigest
    assert IAgentStateRepository is agent_api.IAgentStateRepository
    assert IAgentSignalRepository is agent_api.IAgentSignalRepository
    assert IAgentEvidenceRepository is agent_api.IAgentEvidenceRepository
    assert IAgentModel is agent_api.IAgentModel


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
