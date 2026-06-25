"""Tests for the conversation-history TaskStore port contracts."""

import pytest

from spakky.agent import ConversationTurn, ModelMessage, ModelMessageRole
from spakky.agent.error import AgentDefinitionError


def test_conversation_turn_expect_projects_to_model_message() -> None:
    """대화 turn은 history 재생을 위해 model 요청 메시지로 투영된다."""
    turn = ConversationTurn(
        ModelMessageRole.USER,
        "who was Einstein?",
        metadata={"turn": "1"},
    )

    message = turn.as_model_message()

    assert message == ModelMessage(
        ModelMessageRole.USER,
        "who was Einstein?",
        metadata={"turn": "1"},
    )


def test_conversation_turn_expect_rejects_blank_content() -> None:
    """다음 턴을 시드할 수 없는 공백 turn 내용은 거부된다."""
    with pytest.raises(AgentDefinitionError):
        ConversationTurn(ModelMessageRole.ASSISTANT, " ")


def test_conversation_turn_expect_rejects_non_dialogue_role() -> None:
    """transcript는 user/assistant 대화만 담으므로 system role turn은 거부된다."""
    with pytest.raises(AgentDefinitionError):
        ConversationTurn(ModelMessageRole.SYSTEM, "framing")
