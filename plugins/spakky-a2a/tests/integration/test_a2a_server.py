"""End-to-end A2A transport tests over the assembled ASGI app."""

import json
from collections.abc import Sequence

import pytest
from spakky.agent.execution import Agent, AgentSignalKind
from spakky.agent.interfaces.model import ModelStreamEvent

from tests.integration.conftest import (
    AssistantAgent,
    build_app,
    make_client,
)

type JsonObject = dict[str, object]


def _send(method: str, params: JsonObject, request_id: str = "1") -> JsonObject:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _user_message(text: str, message_id: str = "m1") -> JsonObject:
    return {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": message_id,
        }
    }


def _approval_id_from(task_result: JsonObject) -> str:
    """Pull the echoed approval id out of a paused task's status message."""
    status = task_result["status"]
    message = status["message"] if isinstance(status, dict) else {}
    parts = message["parts"] if isinstance(message, dict) else []
    for part in parts if isinstance(parts, list) else []:
        data = part.get("data") if isinstance(part, dict) else None
        if isinstance(data, dict) and isinstance(data.get("approval_id"), str):
            return data["approval_id"]
    raise AssertionError("paused task carried no approval id")


def _sse_status_states(body: str) -> list[str]:
    """Extract the ordered task-status states from an SSE response body."""
    states: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        result = json.loads(line[len("data:") :].strip())["result"]
        if "status" in result:
            states.append(result["status"]["state"])
    return states


@pytest.mark.integration
async def test_agent_card_endpoint_serves_derived_card(
    token_events: Sequence[ModelStreamEvent],
) -> None:
    """The well-known route serves the AgentCard derived from the @Agent."""
    async with make_client(build_app(token_events)) as client:
        response = await client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "assistant"
    assert any(skill["id"].endswith(":write_note") for skill in card["skills"])


@pytest.mark.integration
async def test_message_send_runs_agent_to_completion(
    token_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """A message/send drives the agent to a completed task carrying streamed text."""
    async with make_client(build_app(token_events)) as client:
        response = await client.post(
            rpc_url, json=_send("message/send", _user_message("hi"))
        )

    result = response.json()["result"]
    assert result["status"]["state"] == "completed"
    history_text = "".join(
        part.get("text", "")
        for message in result.get("history", [])
        for part in message.get("parts", [])
    )
    assert "hello " in history_text and "world" in history_text


@pytest.mark.integration
async def test_message_stream_emits_ordered_lifecycle(
    token_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """A message/stream emits submitted -> working -> completed over SSE."""
    async with make_client(build_app(token_events)) as client:
        async with client.stream(
            "POST", rpc_url, json=_send("message/stream", _user_message("hi"))
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = await response.aread()

    states = _sse_status_states(body.decode())
    assert states[0] == "submitted"
    assert "working" in states
    assert states[-1] == "completed"


@pytest.mark.integration
async def test_tasks_get_returns_persisted_task(
    token_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """tasks/get returns the persisted task after a completed run."""
    async with make_client(build_app(token_events)) as client:
        sent = await client.post(
            rpc_url, json=_send("message/send", _user_message("hi"))
        )
        task_id = sent.json()["result"]["id"]

        fetched = await client.post(rpc_url, json=_send("tasks/get", {"id": task_id}))

    assert fetched.json()["result"]["id"] == task_id


@pytest.mark.integration
async def test_tasks_resubscribe_streams_existing_task(
    token_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """tasks/resubscribe opens an SSE stream for an existing task."""
    async with make_client(build_app(token_events)) as client:
        sent = await client.post(
            rpc_url, json=_send("message/send", _user_message("hi"))
        )
        task_id = sent.json()["result"]["id"]

        async with client.stream(
            "POST", rpc_url, json=_send("tasks/resubscribe", {"id": task_id})
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.integration
async def test_tasks_cancel_marks_task_canceled(
    approval_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """tasks/cancel appends a cancel signal and reports a canceled task."""
    async with make_client(build_app(approval_events)) as client:
        sent = await client.post(
            rpc_url, json=_send("message/send", _user_message("write"))
        )
        task_id = sent.json()["result"]["id"]

        canceled = await client.post(
            rpc_url, json=_send("tasks/cancel", {"id": task_id})
        )

    assert canceled.json()["result"]["status"]["state"] == "canceled"


@pytest.mark.integration
async def test_hitl_approval_pause_then_resume_completes(
    approval_events: Sequence[ModelStreamEvent],
    rpc_url: str,
) -> None:
    """A write tool pauses for input, then an approval decision resumes to done."""
    async with make_client(build_app(approval_events)) as client:
        paused = await client.post(
            rpc_url, json=_send("message/send", _user_message("write"))
        )
        paused_result = paused.json()["result"]
        assert paused_result["status"]["state"] == "input-required"
        task_id = paused_result["id"]
        context_id = paused_result["contextId"]
        approval_id = _approval_id_from(paused_result)

        resume_message: JsonObject = {
            "message": {
                "role": "user",
                "taskId": task_id,
                "contextId": context_id,
                "parts": [
                    {
                        "kind": "data",
                        "data": {"approval_id": approval_id, "decision": "approve"},
                    }
                ],
                "messageId": "m2",
            }
        }
        resumed = await client.post(
            rpc_url, json=_send("message/send", resume_message, request_id="2")
        )

    assert resumed.json()["result"]["status"]["state"] == "completed"


@pytest.mark.integration
async def test_durable_agent_accepts_signal_kinds() -> None:
    """The served durable agent declares the HITL signal kinds it consumes."""
    accepted = Agent.get(AssistantAgent).spec.accepted_signals

    assert AgentSignalKind.APPROVAL_DECISION in accepted
    assert AgentSignalKind.CANCEL in accepted
