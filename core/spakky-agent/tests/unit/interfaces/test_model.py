"""Tests for agent model interface contracts."""

from collections.abc import AsyncIterator

import pytest

from spakky.agent import (
    IAgentModel,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    SamplingOptions,
    StructuredOutputSpec,
)


class FakeAgentModel(IAgentModel):
    """Test double for the abstract model port."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=f"complete:{len(request.messages)}",
            structured_output={"ok": True},
        )

    async def _events(self) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(kind=ModelStreamEventKind.TEXT_DELTA, text="hi")
        yield ModelStreamEvent(kind=ModelStreamEventKind.FINAL, payload={"ok": True})

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        return self._events()


def test_model_request_expect_provider_neutral_structured_output_contract() -> None:
    """ModelRequest가 JSON schema 기반 structured output spec을 보존한다."""
    constraint = JsonSchemaConstraint(schema={"type": "object"})
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        structured_output=StructuredOutputSpec(constraint=constraint),
        sampling=SamplingOptions(temperature=0.2, max_tokens=64),
    )

    assert request.messages[0].role == ModelMessageRole.USER
    assert request.structured_output is not None
    assert request.structured_output.constraint is constraint
    assert request.sampling.temperature == 0.2
    assert request.sampling.max_tokens == 64


@pytest.mark.asyncio
async def test_agent_model_expect_complete_and_stream_are_typed_port_methods() -> None:
    """IAgentModel 구현체가 complete와 stream 계약을 제공한다."""
    model = FakeAgentModel()
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    response = await model.complete(request)
    events = [event async for event in model.stream(request)]

    assert response.content == "complete:1"
    assert response.structured_output == {"ok": True}
    assert events == [
        ModelStreamEvent(kind=ModelStreamEventKind.TEXT_DELTA, text="hi"),
        ModelStreamEvent(kind=ModelStreamEventKind.FINAL, payload={"ok": True}),
    ]
