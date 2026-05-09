"""Tests for vLLM model adapter mapping."""

from collections.abc import AsyncGenerator, Mapping
from typing import override

import pytest
from spakky.agent import (
    ContextPack,
    ContextPackRole,
    JsonObject,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    JsonSchemaConstraint,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)

from spakky.plugins.vllm.client import IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    AbstractVllmError,
    VllmConstrainedDecodingUnsupportedError,
    VllmModelRefusalError,
    VllmResponseError,
    VllmTimeoutError,
    VllmTransportError,
)
from spakky.plugins.vllm.model import VllmAgentModel


class RecordingClient(IVllmChatClient):
    payload: Mapping[str, object] | None
    response: Mapping[str, object]
    stream_chunks: tuple[Mapping[str, object], ...]
    stream_error: AbstractVllmError | None
    stream_call_error: AbstractVllmError | None
    stream_closed: bool

    def __init__(
        self,
        response: Mapping[str, object],
        stream_chunks: tuple[Mapping[str, object], ...] = (),
        stream_error: AbstractVllmError | None = None,
        stream_call_error: AbstractVllmError | None = None,
    ) -> None:
        self.payload = None
        self.response = response
        self.stream_chunks = stream_chunks
        self.stream_error = stream_error
        self.stream_call_error = stream_call_error
        self.stream_closed = False

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
        if self.stream_call_error is not None:
            raise self.stream_call_error
        return self._stream()

    async def _stream(self) -> AsyncGenerator[Mapping[str, object], None]:
        try:
            if self.stream_error is not None:
                raise self.stream_error
            for chunk in self.stream_chunks:
                yield chunk
        finally:
            self.stream_closed = True


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
    assert response.metadata == {"provider": "vllm", "finish_reason": None}
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


async def test_complete_assembles_context_pack_messages_into_payload() -> None:
    """ModelRequest context pack은 assemble_messages() 경로로 payload에 포함된다."""
    client = RecordingClient({"choices": [{"message": {"content": "grounded"}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "answer"),),
        context=(
            ContextPack(
                id="ctx-1",
                content="repo facts",
                source="search",
                role=ContextPackRole.EVIDENCE,
            ),
        ),
    )

    await model.complete(request)

    assert client.payload is not None
    assert client.payload["messages"] == [
        {"role": "user", "content": "answer"},
        {"role": "user", "content": "repo facts"},
    ]


async def test_complete_includes_configured_chat_template_kwargs() -> None:
    """vLLM model-specific chat template kwargs are passed through."""
    client = RecordingClient({"choices": [{"message": {"content": "ok"}}]})
    config = VllmConfig()
    config.chat_template_kwargs["enable_thinking"] = False
    model = VllmAgentModel(config, client)

    await model.complete(
        ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))
    )

    assert client.payload is not None
    assert client.payload["chat_template_kwargs"] == {"enable_thinking": False}


async def test_complete_maps_tool_calling_surface() -> None:
    """tool calling 요청은 OpenAI function tool payload로 변환된다."""
    search_schema = {
        "type": "object",
        "properties": {
            "q": {"type": "string"},
            "limit": {"type": "integer"},
            "exact": {"type": "boolean"},
            "filters": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "empty": {"anyOf": [{"type": "null"}, {"type": "string"}]},
        },
        "required": ["q"],
        "additionalProperties": False,
    }
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
                    parameters=JsonSchemaConstraint(schema=search_schema),
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
                "parameters": search_schema,
                "strict": True,
            },
        }
    ]


async def test_complete_accepts_tool_calls_without_text_content() -> None:
    """tool_calls 중심 assistant 응답은 content가 생략되어도 tool 실행 후보로 수용한다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {"name": "search", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    response = await model.complete(request)

    assert response.content == ""
    assert response.tool_calls[0].name == "search"


async def test_complete_maps_structured_output_and_optional_tool_choice() -> None:
    """structured output과 optional tool choice가 OpenAI-compatible payload에 반영된다."""
    client = RecordingClient({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})
    model = VllmAgentModel(VllmConfig(), client)
    output_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    tool_schema = {"type": "object"}
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=output_schema, strict=False),
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="noop",
                    parameters=JsonSchemaConstraint(schema=tool_schema),
                ),
            ),
            choice=ModelToolChoice.NONE,
        ),
    )

    response = await model.complete(request)

    assert response.structured_output == {"answer": "ok"}
    assert client.payload is not None
    assert client.payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "schema": output_schema,
            "strict": False,
        },
    }
    assert client.payload["structured_outputs"] == {"json": output_schema}
    assert client.payload["tool_choice"] == "none"
    tools = client.payload["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["parameters"] is tool_schema


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
                    parameters=JsonSchemaConstraint(
                        schema={"type": "object"},
                        strict=False,
                    ),
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


async def test_complete_auto_strict_tool_choice_expect_capability_error() -> None:
    """vLLM auto tool choice는 schema constrained decoding 보장을 조용히 가장하지 않는다."""
    client = RecordingClient({"choices": [{"message": {"content": "{}"}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "call tool"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(
                        schema={"type": "object"},
                        strict=True,
                    ),
                ),
            ),
            choice=ModelToolChoice.AUTO,
        ),
    )

    with pytest.raises(VllmConstrainedDecodingUnsupportedError):
        await model.complete(request)


async def test_complete_invalid_structured_output_expect_response_error() -> None:
    """structured output 응답은 tool 실행 후보로 넘어가기 전에 parse/validation 된다."""
    client = RecordingClient({"choices": [{"message": {"content": '{"count":"bad"}'}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(
                schema={
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                    "additionalProperties": False,
                },
            ),
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


async def test_complete_invalid_tool_arguments_expect_response_error() -> None:
    """tool arguments가 schema와 맞지 않으면 ModelToolCall 후보 생성 전에 실패한다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "search",
                                    "arguments": '{"limit":"bad"}',
                                }
                            }
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "call tool"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(
                        schema={
                            "type": "object",
                            "properties": {
                                "q": {"type": "string"},
                                "limit": {"type": "integer"},
                            },
                            "required": ["q"],
                            "additionalProperties": False,
                        },
                    ),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


async def test_complete_none_tool_choice_with_tool_call_expect_response_error() -> None:
    """tool_choice none인데 provider가 tool call을 반환하면 명시적으로 실패한다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "search", "arguments": "{}"}}
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "do not call"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.NONE,
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


async def test_complete_unknown_tool_call_name_expect_response_error() -> None:
    """요청하지 않은 tool 이름은 실행 후보로 정규화하지 않는다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "other", "arguments": "{}"}}
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "call tool"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


async def test_complete_empty_tool_arguments_are_validated() -> None:
    """빈 tool arguments도 schema가 요구하는 필드가 있으면 실패한다."""
    client = RecordingClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "search", "arguments": ""}}
                        ],
                    }
                }
            ],
        }
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "call tool"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(
                        schema={
                            "type": "object",
                            "properties": {"q": {"type": "string"}},
                            "required": ["q"],
                        },
                    ),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


def test_duplicate_tool_schema_names_expect_response_error() -> None:
    """중복 tool name은 provider response 검증 map을 만들 수 없다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))
    tool_calling = ToolCallingSpec(
        tools=(
            ModelToolSpec(
                name="search",
                parameters=JsonSchemaConstraint(schema={"type": "object"}),
            ),
            ModelToolSpec(
                name="search",
                parameters=JsonSchemaConstraint(schema={"type": "object"}),
            ),
        ),
    )

    with pytest.raises(VllmResponseError):
        model._tool_constraints_by_name(tool_calling)


@pytest.mark.parametrize("content", ["", "not-json"])
async def test_complete_malformed_structured_output_expect_response_error(
    content: str,
) -> None:
    """structured output content가 비었거나 JSON이 아니면 실패한다."""
    client = RecordingClient({"choices": [{"message": {"content": content}}]})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema={"type": "object"}),
        ),
    )

    with pytest.raises(VllmResponseError):
        await model.complete(request)


def test_schema_validator_accepts_core_generated_schema_shapes() -> None:
    """로컬 schema validator는 core가 생성하는 JSON Schema subset을 수용한다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))

    model._validate_json_value("a", {"enum": ["a"], "type": "string"})
    model._validate_json_value("a", {"enum": ["a"]})
    model._validate_json_value(
        "a", {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    )
    model._validate_json_value(
        {"extra": "ok"},
        {"type": "object", "additionalProperties": True},
    )
    model._validate_json_value(
        {"extra": "ok"},
        {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    )
    model._validate_json_value(("a", 1), {"type": "array"})
    model._validate_json_value(
        ("a", 1),
        {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}]},
    )
    model._validate_json_value(
        ("a", "b"), {"type": "array", "items": {"type": "string"}}
    )
    model._validate_json_value(("a",), {"type": "array", "minItems": 1, "maxItems": 2})


@pytest.mark.parametrize(
    "value,schema",
    [
        ("a", {"enum": "bad"}),
        ("a", {"enum": ["b"]}),
        ("a", {"anyOf": "bad"}),
        ("a", {"anyOf": ["bad"]}),
        ("a", {"anyOf": [{"type": "integer"}]}),
        (1, {"type": "object"}),
        ({}, {"type": "object", "required": "bad"}),
        ({}, {"type": "object", "required": [1]}),
        ({"x": 1}, {"type": "object", "properties": "bad"}),
        ({"x": 1}, {"type": "object", "properties": {"x": "bad"}}),
        ({"x": 1}, {"type": "object", "additionalProperties": False}),
        ({"x": 1}, {"type": "object", "additionalProperties": "bad"}),
        ("a", {"type": "array"}),
        ((), {"type": "array", "minItems": 1}),
        (("a", "b"), {"type": "array", "maxItems": 1}),
        (("a",), {"type": "array", "items": "bad"}),
        ((), {"type": "array", "prefixItems": [{"type": "string"}]}),
        (("a",), {"type": "array", "prefixItems": "bad"}),
        (("a",), {"type": "array", "prefixItems": ["bad"]}),
        (1, {"type": "string"}),
        (True, {"type": "integer"}),
        (True, {"type": "number"}),
        ("true", {"type": "boolean"}),
        ("null", {"type": "null"}),
    ],
)
def test_schema_validator_rejects_invalid_shapes(
    value: JsonValue,
    schema: JsonObject,
) -> None:
    """schema subset 위반은 모두 provider response error로 표면화된다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))

    with pytest.raises(VllmResponseError):
        model._validate_json_value(value, schema)


async def test_complete_invalid_response_expect_vllm_response_error() -> None:
    """vLLM 응답 shape가 깨졌으면 provider-neutral 응답으로 조용히 변환하지 않는다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(VllmResponseError):
        await model.complete(request)


async def test_complete_refusal_response_expect_model_refusal_error() -> None:
    """non-streaming model refusal은 plugin typed error로 표현된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {"choices": [{"message": {"content": "", "refusal": "blocked"}}]}
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(VllmModelRefusalError):
        await model.complete(request)


async def test_complete_content_filter_finish_expect_model_refusal_error() -> None:
    """content_filter finish reason은 non-streaming refusal error로 표현된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {
                "choices": [
                    {"finish_reason": "content_filter", "message": {"content": ""}}
                ]
            }
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    with pytest.raises(VllmModelRefusalError):
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


async def test_stream_maps_token_deltas_usage_and_done_event() -> None:
    """stream()은 vLLM token delta와 usage를 provider-neutral event로 변환한다."""
    client = RecordingClient(
        {"choices": []},
        stream_chunks=(
            {"choices": [{"delta": {"content": "Hel"}, "finish_reason": None}]},
            {
                "choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        ),
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0] == ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="Hel",
        metadata={"provider": "vllm"},
    )
    assert events[1] == ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="lo",
        metadata={"provider": "vllm"},
    )
    assert events[2].kind == ModelStreamEventKind.DONE
    assert events[2].usage is not None
    assert events[2].usage.total_tokens == 5
    assert events[2].metadata == {"provider": "vllm", "finish_reason": "stop"}
    assert client.payload is not None
    assert client.payload["stream"] is True
    assert client.payload["stream_options"] == {"include_usage": True}


async def test_stream_emits_structured_output_event_after_json_completion() -> None:
    """streaming structured output은 token 이후 검증된 STRUCTURED_OUTPUT event를 낸다."""
    client = RecordingClient(
        {"choices": []},
        stream_chunks=(
            {"choices": [{"delta": {"content": '{"answer"'}}]},
            {"choices": [{"delta": {"content": ':"ok"}'}, "finish_reason": "stop"}]},
        ),
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "json"),),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            ),
        ),
    )

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.TOKEN_DELTA
    assert events[1].kind == ModelStreamEventKind.TOKEN_DELTA
    assert events[2] == ModelStreamEvent(
        kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
        structured_output={"answer": "ok"},
        metadata={"provider": "vllm"},
    )
    assert events[3].kind == ModelStreamEventKind.DONE
    assert client.payload is not None
    assert client.payload["structured_outputs"] == {
        "json": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
    }


async def test_stream_maps_tool_call_chunks_after_tool_finish_reason() -> None:
    """streaming tool_call delta 조각은 완료 시점에 ModelToolCall 후보가 된다."""
    client = RecordingClient(
        {"choices": []},
        stream_chunks=(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q":"spa',
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": 'kky","limit":2}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ),
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.TOOL_CALL_CANDIDATE
    assert events[0].tool_call is not None
    assert events[0].tool_call.name == "search"
    assert events[0].tool_call.call_id == "call-1"
    assert events[0].tool_call.arguments == {"q": "spakky", "limit": 2}
    assert events[1].kind == ModelStreamEventKind.DONE
    assert events[1].metadata == {"provider": "vllm", "finish_reason": "tool_calls"}


async def test_stream_maps_usage_only_chunk_to_done_usage() -> None:
    """usage-only final chunk는 DONE event usage로 보존된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {"choices": []},
            stream_chunks=(
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 1,
                        "total_tokens": 5,
                    },
                },
            ),
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.DONE
    assert events[0].usage is not None
    assert events[0].usage.total_tokens == 5
    assert events[0].metadata == {"provider": "vllm", "finish_reason": None}


async def test_stream_tool_call_chunks_accept_omitted_index_and_function() -> None:
    """tool_call delta가 index/function 조각을 생략해도 후속 조각으로 완성된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {"choices": []},
            stream_chunks=(
                {"choices": [{"delta": {"tool_calls": [{"id": "call-1"}]}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"function": {"name": "search", "arguments": None}}
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            ),
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].tool_call is not None
    assert events[0].tool_call.name == "search"
    assert events[0].tool_call.arguments == {}


async def test_stream_auto_strict_tool_choice_emits_capability_error() -> None:
    """stream()은 지원되지 않는 constrained decoding 조합을 ERROR event로 표면화한다."""
    model = VllmAgentModel(VllmConfig(), RecordingClient({"choices": []}))
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "call tool"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            ),
            choice=ModelToolChoice.AUTO,
        ),
    )

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_constrained_decoding_unsupported"
    assert events[1].kind == ModelStreamEventKind.DONE


async def test_stream_tool_call_finish_without_name_expect_error_event() -> None:
    """tool_call finish 시 name이 없으면 invalid stream chunk error가 된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {"choices": []},
            stream_chunks=(
                {
                    "choices": [
                        {
                            "delta": {"tool_calls": [{"function": {}}]},
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            ),
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_response_error"


async def test_stream_choice_without_delta_expect_done_only() -> None:
    """delta 없는 terminal choice는 token 없이 DONE만 만든다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient(
            {"choices": []},
            stream_chunks=({"choices": [{"finish_reason": "stop"}]},),
        ),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events == [
        ModelStreamEvent(
            kind=ModelStreamEventKind.DONE,
            metadata={"provider": "vllm", "finish_reason": "stop"},
        )
    ]


@pytest.mark.parametrize(
    "chunk,code",
    [
        ({"choices": "bad"}, "vllm_response_error"),
        (
            {"choices": [{"delta": {"refusal": "cannot comply"}}]},
            "model_refusal",
        ),
        (
            {"choices": [{"delta": {}, "finish_reason": "content_filter"}]},
            "model_refusal",
        ),
        (
            {"error": {"code": "provider_down", "message": "try later"}},
            "provider_down",
        ),
    ],
)
async def test_stream_errors_are_typed_model_error_events(
    chunk: Mapping[str, object],
    code: str,
) -> None:
    """invalid chunk, refusal, provider error는 stream ERROR event로 표현된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient({"choices": []}, stream_chunks=(chunk,)),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == code
    assert events[-1].kind == ModelStreamEventKind.DONE


async def test_stream_timeout_is_retryable_model_error_event() -> None:
    """streaming timeout은 retryable ModelError event로 변환된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient({"choices": []}, stream_error=VllmTimeoutError()),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_timeout"
    assert events[0].error.retryable is True
    assert events[1].kind == ModelStreamEventKind.DONE


async def test_stream_transport_error_is_retryable_model_error_event() -> None:
    """streaming transport failure는 retryable ModelError event로 변환된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient({"choices": []}, stream_error=VllmTransportError()),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_transport_error"
    assert events[0].error.retryable is True
    assert events[1].kind == ModelStreamEventKind.DONE


async def test_stream_call_error_is_model_error_event() -> None:
    """client stream 생성 시점의 typed error도 ModelError event로 변환된다."""
    model = VllmAgentModel(
        VllmConfig(),
        RecordingClient({"choices": []}, stream_call_error=VllmTransportError()),
    )
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_transport_error"
    assert events[1].kind == ModelStreamEventKind.DONE


async def test_stream_disabled_emits_typed_error_without_client_call(
    monkeypatch,
) -> None:
    """stream_enabled=false이면 HTTP 호출 없이 명시적 stream disabled event를 낸다."""
    monkeypatch.setenv("SPAKKY_VLLM__STREAM_ENABLED", "false")
    client = RecordingClient({"choices": []})
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    events = [event async for event in model.stream(request)]

    assert events[0].kind == ModelStreamEventKind.ERROR
    assert events[0].error is not None
    assert events[0].error.code == "vllm_streaming_disabled"
    assert events[1].kind == ModelStreamEventKind.DONE
    assert client.payload is None


async def test_stream_cancellation_closes_underlying_stream() -> None:
    """agent cancellation lifecycle은 async generator close로 HTTP stream cleanup에 연결된다."""
    client = RecordingClient(
        {"choices": []},
        stream_chunks=(
            {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "bye"}, "finish_reason": "stop"}]},
        ),
    )
    model = VllmAgentModel(VllmConfig(), client)
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))
    stream = model.stream(request)

    first = await stream.__anext__()
    await stream.aclose()

    assert first.token_delta == "hi"
    assert client.stream_closed is True
