"""AG-UI stdio protocol boundary for CLI adapters.

The stdio boundary intentionally emits protocol payloads only: it accepts a
single AG-UI ``RunAgentInput`` JSON document from stdin or an argument, drives the
same ``AgUiRunDriver`` used by SSE/HTTP/WebSocket adapters, and writes one AG-UI
event JSON payload per stdout line. Rendering, colors, and nested views remain
the responsibility of the consuming UI process.
"""

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import TextIO

from ag_ui.core import RunAgentInput as AgUiRunAgentInput

from spakky.plugins.agui.endpoint import RunDriverFactory, _to_core_input
from spakky.plugins.agui.serialization import sse_frame_payload


@dataclass(frozen=True, slots=True)
class AgUiStdioCommand:
    """Callable command object that CLI plugins can register with their runner."""

    run_driver_factory: RunDriverFactory
    input_stream: TextIO
    output_stream: TextIO
    accept: str | None = None

    async def __call__(self, run_input_json: str | None = None) -> None:
        """Run one AG-UI input from ``run_input_json`` or stdin over stdio."""
        await run_agui_stdio(
            run_driver_factory=self.run_driver_factory,
            input_stream=self.input_stream,
            output_stream=self.output_stream,
            run_input_json=run_input_json,
            accept=self.accept,
        )


async def run_agui_stdio(
    *,
    run_driver_factory: RunDriverFactory,
    input_stream: TextIO,
    output_stream: TextIO,
    run_input_json: str | None = None,
    accept: str | None = None,
) -> None:
    """Drive one AG-UI run from stdio and write AG-UI event payloads to stdout."""
    ag_ui_input = read_agui_run_input(
        input_stream=input_stream,
        run_input_json=run_input_json,
    )
    core_input = _to_core_input(ag_ui_input)
    driver = run_driver_factory(core_input, ag_ui_input, accept)
    async for payload in agui_stdio_payloads(driver):
        output_stream.write(payload)
        output_stream.flush()


def read_agui_run_input(
    *,
    input_stream: TextIO,
    run_input_json: str | None = None,
) -> AgUiRunAgentInput:
    """Parse an AG-UI ``RunAgentInput`` from an argument or stdin."""
    payload = run_input_json if run_input_json is not None else input_stream.read()
    return AgUiRunAgentInput.model_validate_json(payload)


async def agui_stdio_payloads(driver: AsyncIterable[str]) -> AsyncIterator[str]:
    """Yield AG-UI event JSON-lines from an ``AgUiRunDriver``-compatible stream."""
    async for frame in driver:
        yield sse_frame_payload(frame)
