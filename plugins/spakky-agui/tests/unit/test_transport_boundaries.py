"""Unit coverage for AG-UI HTTP stream, WebSocket, and stdio boundaries."""

from collections.abc import AsyncIterator
from io import StringIO
from json import dumps
from typing import cast

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky.agent.inbound import RunAgentInput
from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.http_stream import add_agui_http_stream_endpoint
from spakky.plugins.agui.stdio import AgUiStdioCommand, run_agui_stdio
from spakky.plugins.agui.transport import AgUiRunDriver
from spakky.plugins.agui.websocket import add_agui_websocket_endpoint

_FRAME = 'data: {"type":"RUN_FINISHED"}\n\n'
_PAYLOAD = '{"type":"RUN_FINISHED"}\n'


class _StaticDriver:
    async def __aiter__(self) -> AsyncIterator[str]:
        yield _FRAME


def _run_input() -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def _driver_factory(
    core_input: RunAgentInput,
    ag_ui_input: AgUiRunAgentInput,
    accept: str | None,
) -> AgUiRunDriver:
    assert core_input.instruction == "hello"
    assert ag_ui_input.run_id == "run-1"
    assert accept in {None, "*/*", "application/x-ndjson", "text/event-stream"}
    return cast(AgUiRunDriver, _StaticDriver())


def test_http_stream_endpoint_yields_json_line_payloads() -> None:
    """HTTP stream endpoint strips SSE framing and emits raw AG-UI JSON lines."""
    app = FastAPI()
    add_agui_http_stream_endpoint(
        app,
        run_driver_factory=_driver_factory,
        config=AgUiConfig(),
    )

    response = TestClient(app).post(
        "/agui/stream",
        json=_run_input(),
        headers={"accept": "application/x-ndjson"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text == _PAYLOAD


async def test_run_agui_stdio_reads_stdin_and_writes_payload_lines() -> None:
    """run_agui_stdio reads stdin when no argument is supplied."""
    output_stream = StringIO()

    await run_agui_stdio(
        run_driver_factory=_driver_factory,
        input_stream=StringIO(dumps(_run_input())),
        output_stream=output_stream,
    )

    assert output_stream.getvalue() == _PAYLOAD


async def test_stdio_command_uses_argument_payload_when_present() -> None:
    """AgUiStdioCommand delegates to the stdio runner with explicit JSON input."""
    output_stream = StringIO()
    command = AgUiStdioCommand(
        run_driver_factory=_driver_factory,
        input_stream=StringIO(""),
        output_stream=output_stream,
        accept="text/event-stream",
    )

    await command(dumps(_run_input()))

    assert output_stream.getvalue() == _PAYLOAD


def test_websocket_endpoint_streams_driver_frames() -> None:
    """WebSocket endpoint maps each client RunAgentInput and streams frames back."""
    app = FastAPI()
    add_agui_websocket_endpoint(
        app,
        run_driver_factory=_driver_factory,
        config=AgUiConfig(),
    )
    client = TestClient(app)

    with client.websocket_connect("/agui/ws") as websocket:
        websocket.send_json(_run_input())
        assert websocket.receive_text() == _FRAME
