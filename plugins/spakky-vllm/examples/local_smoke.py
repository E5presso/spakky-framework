"""Run a local vLLM complete/stream/tool smoke path from the command line."""

from asyncio import run
from collections.abc import AsyncIterator, Mapping

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


def _text_request(prompt: str) -> ModelRequest:
    return ModelRequest(
        messages=(
            ModelMessage(ModelMessageRole.SYSTEM, "Answer briefly."),
            ModelMessage(ModelMessageRole.USER, prompt),
        ),
        sampling=SamplingOptions(temperature=0.0, max_tokens=48),
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


async def _stream_lines(
    stream: AsyncIterator[ModelStreamEvent],
) -> AsyncIterator[str]:
    async for event in stream:
        if event.kind == ModelStreamEventKind.TOKEN_DELTA:
            yield f"TOKEN_DELTA {event.token_delta}"
        elif event.kind == ModelStreamEventKind.TOOL_CALL_CANDIDATE:
            yield f"TOOL_CALL {event.tool_call}"
        elif event.kind == ModelStreamEventKind.ERROR:
            yield f"ERROR {event.error}"
        elif event.kind == ModelStreamEventKind.DONE:
            yield f"DONE usage={event.usage}"


async def main() -> None:
    """Run the smoke path using SPAKKY_VLLM__* environment settings."""
    model = VllmAgentModel(VllmConfig(), HttpxVllmChatClient())

    complete_response = await model.complete(_text_request("Say spakky-vllm-smoke."))
    print(f"COMPLETE {complete_response.content}")

    async for line in _stream_lines(model.stream(_text_request("Say stream-ok."))):
        print(line)

    tool_response = await model.complete(_tool_request())
    for tool_call in tool_response.tool_calls:
        print(f"TOOL_CALL {tool_call.name} {tool_call.arguments}")


if __name__ == "__main__":
    run(main())
