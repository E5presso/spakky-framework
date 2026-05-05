"""Tests for agent execution contracts."""

import pytest

from spakky.agent import (
    Agent,
    AgentDefinitionError,
    AgentExecutionSpec,
    AgentSignalKind,
    RecoveryStrategy,
    StreamingExposureMode,
)


def test_agent_execution_spec_expect_defaults_are_non_durable_and_balanced() -> None:
    """기본 실행 spec은 production persistence fallback을 암시하지 않는다."""
    spec = AgentExecutionSpec()

    assert spec.accepted_signals == ()
    assert spec.recovery == RecoveryStrategy.NONE
    assert spec.streaming_exposure_mode == StreamingExposureMode.BALANCED
    assert spec.timeout_seconds is None
    assert spec.delegation_allowed is False
    assert spec.metadata == {}


def test_agent_execution_spec_expect_accepts_adr_signal_vocabulary() -> None:
    """ADR-0009의 signal vocabulary를 tuple 계약으로 표현한다."""
    spec = AgentExecutionSpec(
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )

    assert spec.accepted_signals == (
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
    )
    assert spec.recovery == RecoveryStrategy.ACTION_BOUNDARY


def test_agent_execution_spec_expect_rejects_non_positive_timeout() -> None:
    """bootstrap 전 definition 단계에서 잘못된 timeout을 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(timeout_seconds=0)


def test_agent_expect_wraps_execution_spec_metadata() -> None:
    """Agent public metadata가 execution spec을 보존한다."""
    spec = AgentExecutionSpec(delegation_allowed=True)

    agent = Agent(spec=spec)

    assert agent.spec is spec
