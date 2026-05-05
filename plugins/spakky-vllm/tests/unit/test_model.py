"""Tests for vLLM model adapter mapping."""

from collections.abc import Mapping
from typing import override

import pytest
from spakky.agent import (
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEvent,
    JsonSchemaConstraint,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)

from spakky.plugins.vllm.client import IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import VllmResponseError
from spakky.plugins.vllm.model import VllmAgentModel


class RecordingClient(IVllmChatClient):
    payload: Mapping[str, object] | None
    response: Mapping[str, object]

    def __init__(self, response: Mapping[str, object]) -> None:
        self.payload = None
        self.response = response

    @override
    async def complete(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> Mapping[str, object]:
        self.payload = payload
        return self.response


async def test_complete_maps_request_to_openai_payload_and_response() -> None:
    """complete()는 core ModelRequest를 vLLM payload로 바꾸고 응답을 되돌린다."""
    client = RecordingClient(
        {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "be useful"),
            ModelMessage(ModelMessageRole.USER, "hello"),
        ),
        sampling=SamplingOptions(temperature=0.2, top_p=0.9, max_tokens=32),
    )

    response = await model.complete(request)

    assert response.content == "hello"
    assert response.usage.input_tokens == 3
    assert response.usage.output_tokens == 2
    assert response.usage.total_tokens == 5
    assert client.payload == {
        "model": "default",
        "messages": [
            {"role": "system", "content": "be useful"},
            {"role": "user", "content": "hello"},
        ],
        "stream": False,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 32,
    }


async def test_complete_maps_tool_calling_surface() -> None:
    """tool calling 요청은 OpenAI function tool payload로 변환된다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "search",
                                    "arguments": (
                                        '{"q":"spakky",'
                                        '"filters":{"kind":"doc"},'
                                        '"limit":2,"exact":true,'
                                        '"tags":["agent"],"empty":null}'
                                    ),
                                },
                            }
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.EVIDENCE, "repo facts"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    description="Search workspace",
                    parameters=JsonSchemaConstraint(
                        schema={"type": "object", "properties": {}},
                    ),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )

    response = await model.complete(request)

    assert response.tool_calls[0].name == "search"
    assert response.tool_calls[0].arguments == {
        "q": "spakky",
        "filters": {"kind": "doc"},
        "limit": 2,
        "exact": True,
        "tags": ("agent",),
        "empty": None,
    }
    assert response.tool_calls[0].call_id == "call-1"
    assert client.payload is not None
    assert client.payload["messages"] == [{"role": "user", "content": "repo facts"}]
    assert client.payload["tool_choice"] == "required"
    assert client.payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search workspace",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


async def test_complete_maps_structured_output_and_optional_tool_choice() -> None:
    """structured output과 optional tool choice가 OpenAI-compatible payload에 반영된다."""
    client = RecordingClient({"choices": [{"message": {"content": "{}"}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema={"type": "object"}, strict=False),
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="noop",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.NONE,
        ),
    )

    await model.complete(request)

    assert client.payload is not None
    assert client.payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "schema": {"type": "object"},
            "strict": False,
        },
    }
    assert client.payload["tool_choice"] == "none"


async def test_complete_maps_named_structured_output_and_auto_tool_choice() -> None:
    """명시된 structured output 이름과 AUTO tool choice를 payload에 보존한다."""
    client = RecordingClient({"choices": [{"message": {"content": "{}"}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema={"type": "object"}),
            output_type_name="Answer",
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="noop",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.AUTO,
        ),
    )

    await model.complete(request)

    assert client.payload is not None
    response_format = client.payload["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["json_schema"]["name"] == "Answer"
    assert client.payload["tool_choice"] == "auto"


async def test_complete_invalid_response_expect_vllm_response_error() -> None:
    """vLLM 응답 shape가 깨졌으면 provider-neutral 응답으로 조용히 변환하지 않는다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(VllmResponseError):
        await model.complete(request)


@pytest.mark.parametrize(
    "response",
    [
        {"choices": "bad"},
        {"choices": ["bad"]},
        {"choices": [{"message": {"content": 1}}]},
        {"choices": [{"message": {"content": "", "tool_calls": "bad"}}]},
        {"choices": [{"message": {"content": "", "tool_calls": [{"function": {}}]}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [{"id": 1, "function": {"name": "x"}}],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "x", "arguments": "not-json"}}
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "x", "arguments": "[]"}}],
                    }
                }
            ]
        },
        {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": "bad"},
        },
    ],
)
async def test_complete_malformed_provider_fields_expect_vllm_response_error(
    response: Mapping[str, object],
) -> None:
    """provider 세부 필드가 계약과 다르면 명시적 response error로 실패한다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient(response))
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(VllmResponseError):
        await model.complete(request)


def test_json_argument_validation_rejects_non_json_object_shapes() -> None:
    """내부 JSON argument 정규화는 object key/value shape를 보수적으로 검증한다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))

    with pytest.raises(VllmResponseError):
        model._to_json_object({1: "bad"})
    with pytest.raises(VllmResponseError):
        model._to_json_value(object())


async def test_stream_surface_emits_explicit_error_until_streaming_mapper_lands() -> (
    None
):
    """stream()은 후속 mapper 구현 전까지 명시적 ERROR event를 낸다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind.value == "error"
    assert events[0].error is not None
    assert events[0].error.code == "vllm_streaming_not_implemented"
    observed: ModelStreamEvent = events[1]
    assert observed.kind.value == "done"
