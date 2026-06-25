"""Tests for the pluggable context-compaction strategies (ADR-0013 §7)."""

from collections.abc import AsyncIterator
from typing import override

import pytest

from spakky.agent import (
    AgentDefinitionError,
    IAgentModel,
    KeepRecentMessagesCompactionStrategy,
    ProviderManagedCompactionStrategy,
    SummarizeOldTurnsCompactionStrategy,
    TrimToolResultsCompactionStrategy,
)
from spakky.agent.compaction import (
    DEFAULT_SUMMARY_INSTRUCTION,
    SUMMARY_MESSAGE_METADATA_KEY,
    SUMMARY_MESSAGE_METADATA_VALUE,
)
from spakky.agent.interfaces.model import (
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelUsage,
)


class SummarizingModel(IAgentModel):
    """Model double that returns a fixed summary and records the request."""

    def __init__(self, summary: str) -> None:
        self._summary = summary
        self.requests: list[ModelRequest] = []

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(context_window_tokens=8000)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content=self._summary)

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for event in ():  # pragma: no cover - summarize never streams
            yield event


def _user(content: str) -> ModelMessage:
    return ModelMessage(ModelMessageRole.USER, content)


def _assistant(content: str) -> ModelMessage:
    return ModelMessage(ModelMessageRole.ASSISTANT, content)


def _tool(content: str) -> ModelMessage:
    return ModelMessage(ModelMessageRole.TOOL, content)


_NO_USAGE = ModelUsage()
_NO_CAPABILITY = ModelCapability()


async def test_keep_recent_expect_drops_oldest_beyond_window() -> None:
    """슬라이딩 윈도우 전략은 윈도우를 초과한 오래된 메시지를 버린다."""
    history = (_user("1"), _assistant("2"), _user("3"), _assistant("4"))
    strategy = KeepRecentMessagesCompactionStrategy(max_messages=2)

    compacted = await strategy.compact(history, _NO_USAGE, _NO_CAPABILITY)

    assert compacted == (_user("3"), _assistant("4"))


async def test_keep_recent_expect_passes_short_history_through() -> None:
    """윈도우보다 짧은 이력은 슬라이딩 윈도우 전략에서 그대로 통과한다."""
    history = (_user("only"),)
    strategy = KeepRecentMessagesCompactionStrategy(max_messages=5)

    compacted = await strategy.compact(history, _NO_USAGE, _NO_CAPABILITY)

    assert compacted == history


def test_keep_recent_expect_rejects_non_positive_window() -> None:
    """슬라이딩 윈도우 크기는 최소 한 개의 메시지를 남겨야 한다."""
    with pytest.raises(AgentDefinitionError):
        KeepRecentMessagesCompactionStrategy(max_messages=0)


async def test_trim_tool_results_expect_truncates_only_over_budget_tool_messages() -> (
    None
):
    """도구 결과 트리밍은 예산을 초과한 TOOL 메시지 내용만 잘라낸다."""
    history = (
        _user("question"),
        _tool("0123456789"),
        _assistant("answer"),
    )
    strategy = TrimToolResultsCompactionStrategy(max_characters=4)

    compacted = await strategy.compact(history, _NO_USAGE, _NO_CAPABILITY)

    assert compacted == (_user("question"), _tool("0123"), _assistant("answer"))


async def test_trim_tool_results_expect_leaves_within_budget_tool_messages() -> None:
    """예산 이내의 TOOL 메시지는 도구 결과 트리밍에서 변경되지 않는다."""
    history = (_tool("ok"),)
    strategy = TrimToolResultsCompactionStrategy(max_characters=8)

    compacted = await strategy.compact(history, _NO_USAGE, _NO_CAPABILITY)

    assert compacted == history


def test_trim_tool_results_expect_rejects_non_positive_budget() -> None:
    """도구 결과 트리밍 예산은 양수여야 한다."""
    with pytest.raises(AgentDefinitionError):
        TrimToolResultsCompactionStrategy(max_characters=0)


async def test_provider_managed_expect_returns_history_unchanged() -> None:
    """프로바이더 관리 전략은 이력을 그대로 반환한다(프로바이더가 압축 소유)."""
    history = (_user("a"), _assistant("b"))
    strategy = ProviderManagedCompactionStrategy()

    compacted = await strategy.compact(history, _NO_USAGE, _NO_CAPABILITY)

    assert compacted is history


async def test_summarize_expect_replaces_old_turns_with_one_summary() -> None:
    """요약 전략은 keep_recent를 초과한 오래된 턴을 단일 요약 메시지로 대체한다."""
    history = (
        _user("first ask"),
        _assistant("first reply"),
        _user("second ask"),
        _assistant("second reply"),
    )
    model = SummarizingModel(summary="earlier briefing")
    strategy = SummarizeOldTurnsCompactionStrategy(model=model, keep_recent=2)

    compacted = await strategy.compact(history, _NO_USAGE, model.capability)

    assert compacted == (
        ModelMessage(
            ModelMessageRole.EVIDENCE,
            "earlier briefing",
            {SUMMARY_MESSAGE_METADATA_KEY: SUMMARY_MESSAGE_METADATA_VALUE},
        ),
        _user("second ask"),
        _assistant("second reply"),
    )


async def test_summarize_expect_feeds_only_old_turns_to_secondary_model() -> None:
    """요약 전략은 keep_recent 이외의 오래된 턴만 보조 모델에 전달한다."""
    history = (_user("old ask"), _assistant("old reply"), _user("recent ask"))
    model = SummarizingModel(summary="briefing")
    strategy = SummarizeOldTurnsCompactionStrategy(model=model, keep_recent=1)

    await strategy.compact(history, _NO_USAGE, model.capability)

    request = model.requests[0]
    assert request.messages[0] == ModelMessage(
        ModelMessageRole.SYSTEM, DEFAULT_SUMMARY_INSTRUCTION
    )
    assert request.messages[1] == ModelMessage(
        ModelMessageRole.USER, "user: old ask\nassistant: old reply"
    )


async def test_summarize_expect_skips_model_call_when_within_recent_window() -> None:
    """요약 전략은 이력이 keep_recent 이내면 보조 모델을 호출하지 않는다."""
    history = (_user("only ask"),)
    model = SummarizingModel(summary="unused")
    strategy = SummarizeOldTurnsCompactionStrategy(model=model, keep_recent=2)

    compacted = await strategy.compact(history, _NO_USAGE, model.capability)

    assert compacted == history
    assert model.requests == []


async def test_summarize_expect_honors_custom_instruction() -> None:
    """요약 전략은 선언된 커스텀 요약 지시문을 보조 모델에 사용한다."""
    history = (_user("a"), _assistant("b"), _user("c"))
    model = SummarizingModel(summary="s")
    strategy = SummarizeOldTurnsCompactionStrategy(
        model=model,
        keep_recent=1,
        summary_instruction="Condense the dialogue into bullet points.",
    )

    await strategy.compact(history, _NO_USAGE, model.capability)

    assert model.requests[0].messages[0] == ModelMessage(
        ModelMessageRole.SYSTEM, "Condense the dialogue into bullet points."
    )


def test_summarize_expect_rejects_non_positive_recent_window() -> None:
    """요약 전략은 최소 한 개의 최근 메시지를 남겨야 한다."""
    model = SummarizingModel(summary="s")
    with pytest.raises(AgentDefinitionError):
        SummarizeOldTurnsCompactionStrategy(model=model, keep_recent=0)


def test_summarize_expect_rejects_blank_instruction() -> None:
    """요약 전략의 요약 지시문은 공백일 수 없다."""
    model = SummarizingModel(summary="s")
    with pytest.raises(AgentDefinitionError):
        SummarizeOldTurnsCompactionStrategy(
            model=model, keep_recent=1, summary_instruction="   "
        )
