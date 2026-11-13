import json
from collections.abc import MutableMapping
from typing import Any

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.fastapi.routes import sse
from spakky.plugins.fastapi.routes.sse import SseEndpointNotGeneratorError
from tests.apps.sse import StreamJournal

EVENT_STREAM = "text/event-stream"
EVENT_TERMINATOR = "\n\n"


def _json_data_events(body: str) -> list[Any]:
    """Decode a stream body made only of JSON `data:` events."""
    return [
        json.loads(block.removeprefix("data: "))
        for block in body.split(EVENT_TERMINATOR)
        if block
    ]


def test_sse_stream_of_server_sent_events_expect_event_id_data_framing(
    api: FastAPI,
) -> None:
    """ServerSentEvent를 yield하면 event/id/data/retry/comment가 SSE wire format으로 전송된다."""
    with TestClient(api) as client:
        response = client.get("/stream/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(EVENT_STREAM)
    assert response.headers["cache-control"] == "no-cache"
    assert response.text == (
        'event: progress\ndata: {"step": 1}\nid: 1\n\n'
        "event: finished\ndata: done\nid: 2\nretry: 3000\n\n"
        ": bye\n\n"
    )


def test_sse_stream_read_incrementally_expect_events_in_order(api: FastAPI) -> None:
    """stream으로 읽으면 이벤트가 yield 순서대로 한 줄씩 도착한다."""
    with TestClient(api) as client:
        with client.stream("GET", "/stream/events") as response:
            lines = [line for line in response.iter_lines() if line]

    assert lines == [
        "event: progress",
        'data: {"step": 1}',
        "id: 1",
        "event: finished",
        "data: done",
        "id: 2",
        "retry: 3000",
        ": bye",
    ]


def test_sse_stream_of_models_with_path_and_query_expect_json_data_events(
    api: FastAPI,
) -> None:
    """일반 객체를 yield하면 JSON data 이벤트가 되고 path/query 파라미터가 주입된다."""
    with TestClient(api) as client:
        response = client.get("/stream/ticks/2", params={"start": 5})

    assert response.status_code == 200
    assert _json_data_events(response.text) == [{"number": 5}, {"number": 6}]


def test_sse_stream_with_invalid_path_parameter_expect_validation_error(
    api: FastAPI,
) -> None:
    """파라미터 검증 실패는 stream이 시작되기 전에 422로 응답한다."""
    with TestClient(api) as client:
        response = client.get("/stream/ticks/many")

    assert response.status_code == 422


def test_sse_stream_from_sync_generator_expect_events(api: FastAPI) -> None:
    """동기 generator 메서드도 SSE stream으로 전송된다."""
    with TestClient(api) as client:
        response = client.get("/stream/sync")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(EVENT_STREAM)
    assert _json_data_events(response.text) == [{"number": 1}, {"number": 2}]


def test_sse_stream_with_post_method_and_body_expect_events(api: FastAPI) -> None:
    """methods를 지정하면 POST body를 받는 SSE stream이 된다."""
    with TestClient(api) as client:
        response = client.post("/stream/countdown", json={"start": 2})
        get_response = client.get("/stream/countdown")

    assert response.status_code == 200
    assert response.text == 'data: {"remaining": 2}\n\ndata: {"remaining": 1}\n\n'
    assert get_response.status_code == 405


def test_sse_stream_with_request_parameter_expect_request_injected(
    api: FastAPI,
) -> None:
    """Request 파라미터를 선언한 SSE 메서드에 요청 객체가 주입된다."""
    with TestClient(api) as client:
        response = client.get("/stream/request-path")

    assert response.text == 'data: {"path": "/stream/request-path"}\n\n'


def test_sse_protected_stream_with_bearer_expect_auth_context_in_stream(
    api: FastAPI,
) -> None:
    """보호된 SSE 메서드는 generator 본문에서 AuthContext를 읽을 수 있다."""
    with TestClient(api) as client:
        response = client.get(
            "/stream/me", headers={"Authorization": "Bearer subject-1"}
        )

    assert response.status_code == 200
    assert response.text == 'data: {"subject": "subject-1"}\n\n'


def test_sse_protected_stream_without_credential_expect_unauthorized_before_stream(
    api: FastAPI,
) -> None:
    """보호된 SSE 메서드에 credential이 없으면 stream 시작 전에 401로 응답한다."""
    with TestClient(api) as client:
        response = client.get("/stream/me")

    assert response.status_code == 401
    assert not response.headers["content-type"].startswith(EVENT_STREAM)


def test_sse_stream_on_audited_method_expect_aspect_applied(api: FastAPI) -> None:
    """SSE 컨트롤러 메서드에도 AOP aspect가 적용되어 aspect가 감싼 stream이 전송된다."""
    with TestClient(api) as client:
        response = client.get("/stream/audited")

    assert _json_data_events(response.text) == [
        {"audited-by": "aspect"},
        {"audited": "yes"},
    ]


def test_sse_generator_route_declared_with_response_class_expect_stream(
    api: FastAPI,
) -> None:
    """verb 데코레이터에 EventSourceResponse를 지정한 generator 메서드도 SSE로 전송된다."""
    with TestClient(api) as client:
        response = client.get("/stream/native")

    assert response.headers["content-type"].startswith(EVENT_STREAM)
    assert _json_data_events(response.text) == [{"number": 7}]


def test_sse_generator_route_with_explicit_response_model_expect_stream(
    api: FastAPI,
) -> None:
    """response_model을 명시한 SSE generator route도 설정을 그대로 넘겨 stream으로 전송된다."""
    with TestClient(api) as client:
        response = client.get("/stream/declared")

    assert response.headers["content-type"].startswith(EVENT_STREAM)
    assert _json_data_events(response.text) == [{"number": 9}]


def test_sse_route_openapi_expect_event_stream_response_and_route_name(
    api: FastAPI,
) -> None:
    """SSE route는 OpenAPI에 text/event-stream 응답과 지정한 이름·설명으로 기록된다."""
    schema = api.openapi()

    ticks = schema["paths"]["/stream/ticks/{count}"]["get"]
    countdown = schema["paths"]["/stream/countdown"]["post"]
    assert EVENT_STREAM in ticks["responses"]["200"]["content"]
    assert ticks["summary"] == "Ticks"
    assert countdown["summary"] == "Start Countdown"
    assert schema["paths"]["/stream/events"]["get"]["description"] == (
        "Stream explicit server-sent events."
    )


def test_sse_decorator_on_non_generator_method_expect_error() -> None:
    """generator가 아닌 메서드에 @sse를 붙이면 등록 시점에 오류가 발생한다."""
    with pytest.raises(SseEndpointNotGeneratorError):

        @sse("/not-a-stream")
        async def not_a_stream() -> dict[str, str]:
            return {"kind": "plain"}


async def test_sse_stream_client_disconnect_expect_generator_closed(
    app: SpakkyApplication, api: FastAPI
) -> None:
    """client가 연결을 끊으면 끝나지 않는 generator가 취소되고 finally가 실행된다."""
    first_event_received = anyio.Event()
    sent: list[MutableMapping[str, Any]] = []
    request_delivered = False

    async def receive() -> MutableMapping[str, Any]:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await first_event_received.wait()
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_event_received.set()

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream/endless",
        "raw_path": b"/stream/endless",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    with anyio.fail_after(5):
        await api(scope, receive, send)

    bodies = [m["body"] for m in sent if m["type"] == "http.response.body"]
    assert bodies[0] == b'data: {"state": "started"}\n\n'
    assert app.container.get(type_=StreamJournal).entries == ["endless-closed"]
