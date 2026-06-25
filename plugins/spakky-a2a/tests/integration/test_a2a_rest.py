"""End-to-end A2A REST transport tests over HTTP+JSON routes."""

import json
from collections.abc import Sequence

import pytest
from spakky.agent.interfaces.model import ModelStreamEvent

from spakky.plugins.a2a.rest_transport.builder import build_a2a_rest_app
from tests.integration.conftest import (
    AssistantAgent,
    ScriptedModel,
    make_client,
)
from tests.unit.conftest import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)

type JsonObject = dict[str, object]

REST_HEADERS = {"A2A-Version": "1.0"}


def _message_request(text: str, message_id: str = "m1") -> JsonObject:
    return {
        "message": {
            "role": "ROLE_USER",
            "messageId": message_id,
            "parts": [{"text": text}],
        }
    }


def _agent(events: Sequence[ModelStreamEvent]) -> AssistantAgent:
    return AssistantAgent(
        ScriptedModel(events),
        FakeStateRepository(),
        FakeSignalRepository(),
        FakeEvidenceRepository(),
    )


def _rest_app(events: Sequence[ModelStreamEvent]):
    return build_a2a_rest_app(
        _agent(events),
        base_url="http://assistant.local",
        version="1.0.0",
    )


def _stream_states(body: str) -> list[str]:
    states: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[len("data:") :].strip())
        task = payload.get("task")
        if isinstance(task, dict):
            status = task.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                states.append(status["state"])
        status_update = payload.get("statusUpdate")
        if isinstance(status_update, dict):
            status = status_update.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                states.append(status["state"])
    return states


@pytest.mark.integration
async def test_agent_card_advertises_http_json_interface(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """The REST app serves an AgentCard that advertises HTTP+JSON."""
    async with make_client(_rest_app(token_events)) as client:
        response = await client.get("/.well-known/agent-card.json")

    card = response.json()
    interfaces = card["supportedInterfaces"]
    assert interfaces[0]["protocolBinding"] == "HTTP+JSON"


@pytest.mark.integration
async def test_message_send_runs_agent_to_completion_over_rest(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """POST /message:send returns a completed task over HTTP+JSON."""
    async with make_client(_rest_app(token_events)) as client:
        response = await client.post(
            "/message:send",
            json=_message_request("hi"),
            headers=REST_HEADERS,
        )

    task = response.json()["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    history_text = "".join(
        part.get("text", "")
        for message in task.get("history", [])
        for part in message.get("parts", [])
    )
    assert "hello " in history_text and "world" in history_text


@pytest.mark.integration
async def test_message_stream_emits_task_lifecycle_over_rest(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """POST /message:stream emits submitted, working, and completed SSE events."""
    async with make_client(_rest_app(token_events)) as client:
        async with client.stream(
            "POST",
            "/message:stream",
            json=_message_request("hi"),
            headers=REST_HEADERS,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = await response.aread()

    states = _stream_states(body.decode())
    assert states[0] == "TASK_STATE_SUBMITTED"
    assert "TASK_STATE_WORKING" in states
    assert states[-1] == "TASK_STATE_COMPLETED"


@pytest.mark.integration
async def test_tasks_get_returns_persisted_task_over_rest(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """GET /tasks/{id} returns the task persisted by a previous REST send."""
    async with make_client(_rest_app(token_events)) as client:
        sent = await client.post(
            "/message:send",
            json=_message_request("hi"),
            headers=REST_HEADERS,
        )
        task_id = sent.json()["task"]["id"]

        fetched = await client.get(f"/tasks/{task_id}", headers=REST_HEADERS)

    assert fetched.json()["id"] == task_id


@pytest.mark.integration
async def test_tasks_subscribe_route_is_available_over_rest(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """GET /tasks/{id}:subscribe dispatches to the SDK subscribe endpoint."""
    async with make_client(_rest_app(token_events)) as client:
        sent = await client.post(
            "/message:send",
            json=_message_request("hi"),
            headers=REST_HEADERS,
        )
        task_id = sent.json()["task"]["id"]

        response = await client.get(
            f"/tasks/{task_id}:subscribe",
            headers=REST_HEADERS,
        )

    assert response.status_code == 400
    assert "already completed" in response.text


@pytest.mark.integration
async def test_tasks_cancel_marks_input_required_task_canceled_over_rest(
    approval_events: Sequence[ModelStreamEvent],
) -> None:
    """POST /tasks/{id}:cancel appends the cancel signal and returns canceled."""
    async with make_client(_rest_app(approval_events)) as client:
        sent = await client.post(
            "/message:send",
            json=_message_request("write"),
            headers=REST_HEADERS,
        )
        task = sent.json()["task"]

        canceled = await client.post(
            f"/tasks/{task['id']}:cancel",
            headers=REST_HEADERS,
        )

    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert canceled.json()["status"]["state"] == "TASK_STATE_CANCELED"
