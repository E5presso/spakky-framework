"""Tests for the AG-UI -> core RunAgentInput mapping at the endpoint boundary."""

from collections.abc import AsyncIterator
from typing import cast

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import raises

from spakky.agent.inbound import RunAgentInput
from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import add_agui_endpoint, _to_core_input
from spakky.plugins.agui.error import AgUiRunResolutionError
from spakky.plugins.agui.transport import AgUiRunDriver


class _StaticDriver:
    async def __aiter__(self) -> AsyncIterator[str]:
        yield 'data: {"type":"RUN_FINISHED"}\n\n'


def _ag_ui_input(
    messages: list[dict[str, object]], parent: str | None = None
) -> AgUiRunAgentInput:
    return AgUiRunAgentInput.model_validate(
        {
            "threadId": "conv-1",
            "runId": "run-1",
            "parentRunId": parent,
            "state": None,
            "messages": messages,
            "tools": [],
            "context": [],
            "forwardedProps": None,
        }
    )


def test_to_core_input_maps_ids_and_last_user_message() -> None:
    """AG-UI 입력이 state/conversation/instruction 코어 필드로 매핑된다."""
    core = _to_core_input(
        _ag_ui_input(
            [
                {"id": "u1", "role": "user", "content": "first"},
                {"id": "a1", "role": "assistant", "content": "ack"},
                {"id": "u2", "role": "user", "content": "second"},
            ]
        )
    )

    assert core.state_id == "run-1"
    assert core.conversation_id == "conv-1"
    assert core.instruction == "second"
    assert core.resume is False


def test_to_core_input_forwards_parent_run_id() -> None:
    """parentRunId가 코어 parent_run_id로 전달된다."""
    core = _to_core_input(
        _ag_ui_input([{"id": "u1", "role": "user", "content": "hi"}], parent="parent-9")
    )

    assert core.parent_run_id == "parent-9"


def test_to_core_input_without_parent_run_id_sets_none() -> None:
    """parentRunId가 없으면 코어 parent_run_id가 None이다."""
    core = _to_core_input(_ag_ui_input([{"id": "u1", "role": "user", "content": "hi"}]))

    assert core.parent_run_id is None


def test_to_core_input_skips_non_text_user_message() -> None:
    """가장 최근 user 메시지의 content가 텍스트가 아니면 그 앞의 텍스트로 fallback한다."""
    core = _to_core_input(
        _ag_ui_input(
            [
                {"id": "u1", "role": "user", "content": "earlier text"},
                {
                    "id": "u2",
                    "role": "user",
                    "content": [{"type": "text", "text": "multimodal"}],
                },
            ]
        )
    )

    assert core.instruction == "earlier text"


def test_to_core_input_without_user_message_raises() -> None:
    """user 메시지가 없으면 AgUiRunResolutionError를 던진다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input([{"id": "a1", "role": "assistant", "content": "ack"}])
        )


def test_add_agui_endpoint_invokes_driver_factory_with_mapped_input() -> None:
    """FastAPI endpoint가 AG-UI JSON을 코어 입력으로 변환해 driver에 연결한다."""
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]] = []
    app = FastAPI()

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        captured.append((core_input, ag_ui_input, accept))
        return cast(AgUiRunDriver, _StaticDriver())

    add_agui_endpoint(
        app,
        run_driver_factory=run_driver_factory,
        config=AgUiConfig(),
    )

    response = TestClient(app).post(
        "/agui",
        json={
            "threadId": "conv-1",
            "runId": "run-1",
            "state": None,
            "messages": [{"id": "u1", "role": "user", "content": "hello"}],
            "tools": [],
            "context": [],
            "forwardedProps": None,
        },
        headers={"accept": "text/event-stream"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == 'data: {"type":"RUN_FINISHED"}\n\n'
    core_input, ag_ui_input, accept = captured[0]
    assert core_input.instruction == "hello"
    assert ag_ui_input.thread_id == "conv-1"
    assert accept == "text/event-stream"
