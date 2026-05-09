"""Acceptance tests for the vLLM agent model adapter."""

from collections.abc import AsyncGenerator, Mapping
from typing import override

from spakky.agent import (
    JsonObject,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)

from spakky.plugins.vllm.client import IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel


async def test_vllm_acceptance_fake_expect_streaming_tokens_structured_output_and_tool_call() -> (
    None
):
    """CI-safe fake stream이 token, structured output, tool call을 core event로 매핑한다."""
    client = _FakeVllmClient(
        stream_chunks=(
            {
                "choices": [
                    {
                        "delta": {"content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            },
        ),
    )
    model = VllmAgentModel(VllmConfig(), client)

    events = [event async for event in model.stream(_structured_request())]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.STRUCTURED_OUTPUT,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].token_delta == '{"answer":"ok"}'
    assert events[1].structured_output == {"answer": "ok"}
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 7
    assert client.payload is not None
    assert client.payload["stream"] is True
    assert client.payload["stream_options"] == {"include_usage": True}
    assert client.payload["structured_outputs"] == {
        "json": _structured_schema(),
    }

    tool_client = _FakeVllmClient(
        response={
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "lookup_weather",
                                    "arguments": '{"city":"Seoul","unit":"celsius"}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
    )
    response = await VllmAgentModel(VllmConfig(), tool_client).complete(_tool_request())

    assert response.tool_calls[0].name == "lookup_weather"
    assert response.tool_calls[0].arguments == {
        "city": "Seoul",
        "unit": "celsius",
    }
    assert tool_client.payload is not None
    assert tool_client.payload["tool_choice"] == "required"


class _FakeVllmClient(IVllmChatClient):
    def __init__(
        self,
        response: Mapping[str, object] | None = None,
        stream_chunks: tuple[Mapping[str, object], ...] = (),
    ) -> None:
        self.payload: Mapping[str, object] | None = None
        self.response = response or {"choices": [{"message": {"content": "ok"}}]}
        self.stream_chunks = stream_chunks

    @override
    async def complete(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> Mapping[str, object]:
        self.payload = payload
        return self.response

    @override
    def stream(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> AsyncGenerator[Mapping[str, object], None]:
        self.payload = payload
        return self._stream()

    async def _stream(self) -> AsyncGenerator[Mapping[str, object], None]:
        for chunk in self.stream_chunks:
            yield chunk


def _structured_request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "return json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=_structured_schema())
        ),
        sampling=SamplingOptions(temperature=0.0, max_tokens=32),
    )


def _structured_schema() -> JsonObject:
    schema: JsonObject = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    return schema


def _tool_request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "weather in Seoul"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="lookup_weather",
                    description="Look up weather.",
                    parameters=JsonSchemaConstraint(
                        schema={
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                                "unit": {"type": "string"},
                            },
                            "required": ["city", "unit"],
                            "additionalProperties": False,
                        }
                    ),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )
