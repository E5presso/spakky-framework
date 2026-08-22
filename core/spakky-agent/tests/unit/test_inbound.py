"""Tests for the RunAgentInput inbound run contract."""

import pytest

from spakky.agent import ModelMessage, ModelMessageRole, ModelSelection, RunAgentInput
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


def test_run_agent_input_expect_model_selection_carried() -> None:
    """요청별 model selection은 inbound contract에 typed field로 보존된다."""
    selection = ModelSelection(model_ref="support/primary")
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="do it",
        model_selection=selection,
    )

    assert run_input.model_selection is selection


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


def test_run_agent_input_expect_rejects_blank_parent_run_id() -> None:
    """공백 parent_run_id는 delegation parent linkage로 쓸 수 없어 거부된다."""
    with pytest.raises(AgentDefinitionError):
        RunAgentInput(state_id="run-1", instruction="do it", parent_run_id=" ")


def test_run_agent_input_expect_defaults_message_history_empty() -> None:
    """클라이언트 주입 이력을 생략하면 빈 history로 단일턴 시드를 의미한다."""
    run_input = RunAgentInput(state_id="run-1", instruction="do it")

    assert run_input.message_history == ()


def test_run_agent_input_expect_client_injected_history_carried() -> None:
    """클라이언트가 주입한 이전 대화 이력이 inbound 입력에 그대로 전달된다."""
    history = (
        ModelMessage(ModelMessageRole.USER, "who was Einstein?"),
        ModelMessage(ModelMessageRole.ASSISTANT, "a physicist"),
    )

    run_input = RunAgentInput(
        state_id="run-2",
        instruction="his famous equation?",
        message_history=history,
    )

    assert run_input.message_history == history
