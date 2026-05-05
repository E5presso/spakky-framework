"""Tests for agent model interface contracts."""

from collections.abc import AsyncIterator

import pytest

from spakky.agent import (
    IAgentModel,
    JsonSchemaConstraint,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)


class FakeAgentModel(IAgentModel):
    """Test double for the abstract model port."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=f"complete:{len(request.messages)}",
            structured_output={"ok": True},
            tool_calls=(
                ModelToolCall(name="search_docs", arguments={"query": "agent"}),
            ),
        )

    async def _events(self) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hi",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(name="search_docs", arguments={"query": "agent"}),
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output={"ok": True},
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=ModelError(
                code="rate_limited", message="retry later", retryable=True
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        return self._events()


def test_model_request_expect_provider_neutral_structured_output_contract() -> None:
    """ModelRequest가 JSON schema 기반 structured output spec을 보존한다."""
    constraint = JsonSchemaConstraint(schema={"type": "object"})
    tool = ModelToolSpec(
        name="search_docs",
        description="Search documentation",
        parameters=JsonSchemaConstraint(schema={"type": "object"}),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        structured_output=StructuredOutputSpec(constraint=constraint),
        tool_calling=ToolCallingSpec(tools=(tool,), choice=ModelToolChoice.REQUIRED),
        sampling=SamplingOptions(temperature=0.2, max_tokens=64),
        streaming=StreamingOptions(include_usage=True, include_progress=False),
    )

    assert request.messages[0].role == ModelMessageRole.USER
    assert request.structured_output is not None
    assert request.structured_output.constraint is constraint
    assert request.tool_calling is not None
    assert request.tool_calling.tools == (tool,)
    assert request.tool_calling.choice == ModelToolChoice.REQUIRED
    assert request.sampling.temperature == 0.2
    assert request.sampling.max_tokens == 64
    assert request.streaming.include_usage is True
    assert request.streaming.include_progress is False


@pytest.mark.asyncio
async def test_agent_model_expect_complete_and_stream_are_typed_port_methods() -> None:
    """IAgentModel 구현체가 complete와 stream 계약을 제공한다."""
    model = FakeAgentModel()
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    response = await model.complete(request)
    events = [event async for event in model.stream(request)]

    assert response.content == "complete:1"
    assert response.structured_output == {"ok": True}
    assert response.tool_calls == (
        ModelToolCall(name="search_docs", arguments={"query": "agent"}),
    )
    assert events == [
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hi",
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(name="search_docs", arguments={"query": "agent"}),
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output={"ok": True},
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=ModelError(
                code="rate_limited", message="retry later", retryable=True
            ),
        ),
        ModelStreamEvent(kind=ModelStreamEventKind.DONE),
    ]


def test_model_stream_event_kind_expect_issue_216_required_vocabulary() -> None:
    """Model stream event가 #216 수용 기준의 canonical event kind를 노출한다."""
    assert {kind.value for kind in ModelStreamEventKind} == {
        "token_delta",
        "tool_call_candidate",
        "structured_output",
        "progress",
        "error",
        "done",
    }
