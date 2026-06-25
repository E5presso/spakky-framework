"""Tests for the RunAgentInput inbound run contract."""

import pytest

from spakky.agent import RunAgentInput
from spakky.agent.error import AgentDefinitionError


def test_run_agent_input_expect_defaults_conversation_to_state_id() -> None:
    """conversation_id가 없으면 run id가 단일턴 대화 식별자가 된다."""
    run_input = RunAgentInput(state_id="run-1", instruction="do it")

    assert run_input.effective_conversation_id == "run-1"


def test_run_agent_input_expect_explicit_conversation_id_preserved() -> None:
    """명시한 conversation_id는 멀티턴 식별자로 그대로 유지된다."""
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="do it",
        conversation_id="thread-9",
    )

    assert run_input.effective_conversation_id == "thread-9"


def test_run_agent_input_expect_resume_flag_carried() -> None:
    """resume 플래그가 inbound 입력에 그대로 전달된다."""
    run_input = RunAgentInput(state_id="run-1", instruction="do it", resume=True)

    assert run_input.resume is True


def test_run_agent_input_expect_rejects_blank_state_id() -> None:
    """run을 상관시킬 수 없는 공백 state_id는 거부된다."""
    with pytest.raises(AgentDefinitionError):
        RunAgentInput(state_id=" ", instruction="do it")


def test_run_agent_input_expect_rejects_blank_instruction() -> None:
    """모델 요청을 시드할 수 없는 공백 instruction은 거부된다."""
    with pytest.raises(AgentDefinitionError):
        RunAgentInput(state_id="run-1", instruction=" ")


def test_run_agent_input_expect_rejects_blank_conversation_id() -> None:
    """공백 conversation_id는 멀티턴 식별자로 쓸 수 없어 거부된다."""
    with pytest.raises(AgentDefinitionError):
        RunAgentInput(state_id="run-1", instruction="do it", conversation_id=" ")
