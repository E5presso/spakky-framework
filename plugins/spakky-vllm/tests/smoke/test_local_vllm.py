"""Opt-in smoke tests against a local vLLM OpenAI-compatible endpoint."""

from collections.abc import Mapping
from os import environ

import httpx
import pytest
from spakky.agent import (
    JsonSchemaConstraint,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolChoice,
    ModelToolSpec,
    SamplingOptions,
    ToolCallingSpec,
)

from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel

SMOKE_ENV = "SPAKKY_VLLM_SMOKE"
SMOKE_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _smoke_enabled() -> bool:
    return environ.get(SMOKE_ENV, "").casefold() in SMOKE_TRUE_VALUES


async def _local_smoke_model() -> VllmAgentModel:
    if not _smoke_enabled():
        pytest.skip(f"set {SMOKE_ENV}=1 to run local vLLM smoke tests")

    config = VllmConfig()
    models_url = f"{config.endpoint_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(models_url)
            response.raise_for_status()
    except httpx.HTTPError as e:
        pytest.skip(f"local vLLM endpoint unavailable at {models_url}: {e!s}")

    return VllmAgentModel(config, HttpxVllmChatClient())


def _text_request(prompt: str) -> ModelRequest:
    return ModelRequest(
        messages=(
            ModelMessage(
                ModelMessageRole.SYSTEM,
                "Return a concise plain text answer for a smoke test.",
            ),
            ModelMessage(ModelMessageRole.USER, prompt),
        ),
        sampling=SamplingOptions(temperature=0.0, max_tokens=32),
    )


def _tool_request() -> ModelRequest:
    tool_schema: Mapping[str, JsonValue] = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["city", "unit"],
        "additionalProperties": False,
    }
    return ModelRequest(
        messages=(
            ModelMessage(
                ModelMessageRole.SYSTEM,
                "Use the provided tool instead of answering directly.",
            ),
            ModelMessage(
                ModelMessageRole.USER,
                "Call lookup_weather for Seoul using celsius.",
            ),
        ),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="lookup_weather",
                    description="Look up a city's current weather.",
                    parameters=JsonSchemaConstraint(schema=tool_schema),
                ),
            ),
            choice=ModelToolChoice.REQUIRED,
        ),
        sampling=SamplingOptions(temperature=0.0, max_tokens=96),
    )


async def test_local_vllm_complete_smoke_expect_text_response() -> None:
    """local vLLM complete() returns a non-empty model response when opted in."""
    model = await _local_smoke_model()

    response = await model.complete(_text_request("Say spakky-vllm-smoke."))

    assert response.content.strip() != ""


async def test_local_vllm_stream_smoke_expect_token_delta_and_done() -> None:
    """local vLLM stream() yields token deltas and a terminal DONE event."""
    model = await _local_smoke_model()
    events: list[ModelStreamEvent] = []

    async for event in model.stream(_text_request("Say stream-ok.")):
        events.append(event)

    errors = tuple(event.error for event in events if event.error is not None)
    token_text = "".join(
        event.token_delta or ""
        for event in events
        if event.kind == ModelStreamEventKind.TOKEN_DELTA
    )
    assert errors == ()
    assert token_text.strip() != ""
    assert events[-1].kind == ModelStreamEventKind.DONE


async def test_local_vllm_tool_schema_smoke_expect_tool_call() -> None:
    """local vLLM required tool choice returns schema-validated tool arguments."""
    model = await _local_smoke_model()

    response = await model.complete(_tool_request())

    matching_calls = tuple(
        call for call in response.tool_calls if call.name == "lookup_weather"
    )
    assert len(matching_calls) == 1
    assert matching_calls[0].arguments["city"] != ""
    assert matching_calls[0].arguments["unit"] in ("celsius", "fahrenheit")
