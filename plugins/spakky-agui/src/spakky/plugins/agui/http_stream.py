"""Mount the AG-UI HTTP chunked streaming endpoint on a FastAPI application.

``add_agui_http_stream_endpoint`` registers a ``POST {config.http_stream_path}``
route that accepts an AG-UI ``RunAgentInput`` and streams encoded AG-UI event
payloads as sequential JSON-line response chunks. It intentionally does not emit
SSE ``data:`` framing; clients that want SSE should keep using
``add_agui_endpoint``.
"""

from collections.abc import AsyncIterable, AsyncIterator

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory, _to_core_input
from spakky.plugins.agui.serialization import sse_frame_payload

HTTP_STREAM_MEDIA_TYPE = "application/x-ndjson"
"""Media type for AG-UI HTTP streaming chunks."""


def add_agui_http_stream_endpoint(
    app: FastAPI,
    *,
    run_driver_factory: RunDriverFactory,
    config: AgUiConfig,
) -> None:
    """Register the AG-UI HTTP streaming endpoint at ``config.http_stream_path``."""

    async def run_agui_http_stream(request: Request) -> StreamingResponse:
        ag_ui_input = AgUiRunAgentInput.model_validate(await request.json())
        core_input = _to_core_input(ag_ui_input)
        driver = run_driver_factory(
            core_input,
            ag_ui_input,
            request.headers.get("accept"),
        )
        return StreamingResponse(
            _http_stream_chunks(driver),
            media_type=HTTP_STREAM_MEDIA_TYPE,
        )

    app.add_api_route(config.http_stream_path, run_agui_http_stream, methods=["POST"])


async def _http_stream_chunks(driver: AsyncIterable[str]) -> AsyncIterator[str]:
    async for frame in driver:
        yield sse_frame_payload(frame)
