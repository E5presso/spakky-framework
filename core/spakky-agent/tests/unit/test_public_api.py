"""Tests for spakky-agent public API exports."""

import spakky.agent as agent_api
from spakky.agent import (
    IAgentModel,
    Agent,
    AgentBootstrapError,
    AgentDefinitionError,
    AgentEvidence,
    AgentExecutionSpec,
    IAgentEvidenceRepository,
    AgentSignal,
    AgentState,
    IAgentSignalRepository,
    IAgentStateRepository,
    AgentYield,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)
from spakky.agent.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_public_api_expect_exports_required_agent_surface() -> None:
    """이슈 #213이 요구한 public import surface를 노출하는지 검증한다."""
    required_exports = {
        "Agent",
        "AgentExecutionSpec",
        "AgentYield",
        "AgentState",
        "AgentSignal",
        "AgentEvidence",
        "IAgentStateRepository",
        "IAgentSignalRepository",
        "IAgentEvidenceRepository",
        "IAgentModel",
    }

    exported = set(agent_api.__all__)

    assert required_exports <= exported
    assert Agent is agent_api.Agent
    assert AgentExecutionSpec is agent_api.AgentExecutionSpec
    assert AgentYield is agent_api.AgentYield
    assert AgentState is agent_api.AgentState
    assert AgentSignal is agent_api.AgentSignal
    assert AgentEvidence is agent_api.AgentEvidence
    assert IAgentStateRepository is agent_api.IAgentStateRepository
    assert IAgentSignalRepository is agent_api.IAgentSignalRepository
    assert IAgentEvidenceRepository is agent_api.IAgentEvidenceRepository
    assert IAgentModel is agent_api.IAgentModel


def test_public_api_expect_exports_model_contract_types() -> None:
    """IAgentModel이 사용하는 provider-neutral request/response 타입을 노출한다."""
    assert ModelRequest is agent_api.ModelRequest
    assert ModelResponse is agent_api.ModelResponse
    assert ModelStreamEvent is agent_api.ModelStreamEvent


def test_public_api_expect_exports_custom_error_hierarchy() -> None:
    """bootstrap/definition 오류가 custom error 계층으로 표현되는지 검증한다."""
    assert issubclass(AgentDefinitionError, agent_api.AbstractSpakkyAgentError)
    assert issubclass(AgentBootstrapError, agent_api.AbstractSpakkyAgentError)


def test_initialize_expect_registers_no_production_fallbacks() -> None:
    """core package 초기화가 persistence/model fallback 구현을 등록하지 않는다."""
    app = SpakkyApplication(ApplicationContext())

    before = dict(app.container.pods)
    initialize(app)

    assert app.container.pods == before
