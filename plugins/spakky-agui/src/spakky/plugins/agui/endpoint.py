"""Mount the AG-UI SSE endpoint on a FastAPI application.

``add_agui_endpoint`` registers a single ``POST {config.sse_path}`` route that
accepts an AG-UI ``RunAgentInput`` and streams the run back as
``text/event-stream``. It owns the protocol-boundary translation that neither
the bridge nor the projector should know about: it maps the AG-UI input shape
(``threadId`` / ``runId`` / ``messages`` / ``parentRunId``) onto the neutral core
``RunAgentInput`` and, when the input carries a resumed approval decision, queues
that decision before the run is driven.

The application author supplies a ``run_driver_factory`` that resolves the
concrete ``@Agent`` for the request and returns a ready ``AgUiRunDriver``. The
endpoint stays agnostic about which agent answers, mirroring pydantic-ai's
``add_*_fastapi_endpoint`` pattern and depending on third-party ``fastapi``
directly (ADR-0013 §2) rather than importing the ``spakky-fastapi`` plugin.
"""

from collections.abc import AsyncIterable, Callable

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from spakky.agent.inbound import RunAgentInput

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint_input import to_core_input

SSE_MEDIA_TYPE = "text/event-stream"
"""Media type for the AG-UI server-sent event stream."""

type RunDriverFactory = Callable[
    [RunAgentInput, AgUiRunAgentInput, str | None],
    AsyncIterable[str],
]
"""Resolves the agent run for a request and returns a ready SSE driver.

Receives the mapped core ``RunAgentInput``, the raw AG-UI input (so the factory
can ingest an approval decision against its own signal repository), and the
request ``Accept`` header for the event encoder.
"""


def add_agui_endpoint(
    app: FastAPI,
    *,
    run_driver_factory: RunDriverFactory,
    config: AgUiConfig,
) -> None:
    """Register the AG-UI SSE endpoint on ``app`` at ``config.sse_path``."""

    async def run_agui(request: Request) -> StreamingResponse:
        ag_ui_input = AgUiRunAgentInput.model_validate(await request.json())
        core_input = _to_core_input(ag_ui_input)
        driver = run_driver_factory(
            core_input,
            ag_ui_input,
            request.headers.get("accept"),
        )
        return StreamingResponse(driver, media_type=SSE_MEDIA_TYPE)

    app.add_api_route(config.sse_path, run_agui, methods=["POST"])


def _to_core_input(ag_ui_input: AgUiRunAgentInput) -> RunAgentInput:
    """Map an AG-UI run input onto the neutral core run input.

    ``runId`` is the durable run/state id, ``threadId`` the conversation, and the
    last user message seeds the instruction. ``resume`` is set when the input
    carries an approval decision so the runner replays its paused boundary.
    ``parentRunId`` preserves delegated run ancestry through the neutral core
    attribution path.
    """
    return to_core_input(ag_ui_input)
