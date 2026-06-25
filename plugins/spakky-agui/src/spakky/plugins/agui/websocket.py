"""Mount the AG-UI WebSocket endpoint on a FastAPI application.

``add_agui_websocket_endpoint`` registers a bidirectional WebSocket route. Each
client JSON message is parsed as an AG-UI ``RunAgentInput``, mapped through the
same protocol boundary as the SSE endpoint, and streamed back as encoded AG-UI
event frames over WebSocket text messages.
"""

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory, _to_core_input


def add_agui_websocket_endpoint(
    app: FastAPI,
    *,
    run_driver_factory: RunDriverFactory,
    config: AgUiConfig,
) -> None:
    """Register the AG-UI WebSocket endpoint on ``app`` at ``config.websocket_path``."""

    async def run_agui_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                ag_ui_input = AgUiRunAgentInput.model_validate(
                    await websocket.receive_json()
                )
                core_input = _to_core_input(ag_ui_input)
                driver = run_driver_factory(
                    core_input,
                    ag_ui_input,
                    websocket.headers.get("accept"),
                )
                async for frame in driver:
                    await websocket.send_text(frame)
        except WebSocketDisconnect:
            return

    app.add_api_websocket_route(config.websocket_path, run_agui_websocket)
