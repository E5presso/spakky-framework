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
from spakky.plugins.agui.endpoint_input import (
    RESUME_APPROVAL_INSTRUCTION,
    inbound_run,
)
from spakky.plugins.agui.error import AgUiRunResolutionError
from spakky.plugins.agui.transport import AgUiRunDriver


class _StaticDriver:
    async def __aiter__(self) -> AsyncIterator[str]:
        yield 'data: {"type":"RUN_FINISHED"}\n\n'


def _ag_ui_input(
    messages: list[dict[str, object]],
    parent: str | None = None,
    forwarded: object | None = None,
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
            "forwardedProps": forwarded,
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


def test_to_core_input_forwards_model_selection_and_mcp_metadata() -> None:
    """forwardedProps의 modelSelection과 mcp는 core run input으로 승격된다."""
    core = _to_core_input(
        _ag_ui_input(
            [{"id": "u1", "role": "user", "content": "hi"}],
            forwarded={
                "modelSelection": {
                    "provider": "openrouter",
                    "model": "anthropic/claude-sonnet-4.5",
                    "profile": "coding",
                    "metadata": {"tier": "paid"},
                },
                "mcp": {"servers": ["github"]},
                "metadata": {"tenant": "acme"},
            },
        )
    )

    assert core.model_selection is not None
    assert core.model_selection.provider == "openrouter"
    assert core.model_selection.model == "anthropic/claude-sonnet-4.5"
    assert core.model_selection.profile == "coding"
    assert core.model_selection.metadata == {"tier": "paid"}
    assert core.metadata == {
        "tenant": "acme",
        "mcp": {"servers": ["github"]},
    }


def test_to_core_input_without_forwarded_props_has_no_runtime_overrides() -> None:
    """forwardedProps 생략은 실행별 model/MCP override 없음으로 해석된다."""
    core = _to_core_input(_ag_ui_input([{"id": "u1", "role": "user", "content": "hi"}]))

    assert core.model_selection is None
    assert core.metadata == {}


def test_to_core_input_rejects_non_object_forwarded_props() -> None:
    """forwardedProps가 객체가 아니면 core 입력으로 승격하지 않는다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded=["not", "an", "object"],
            )
        )


def test_to_core_input_allows_forwarded_metadata_without_model_selection() -> None:
    """modelSelection 없이 metadata만 전달해도 run metadata로 승격된다."""
    core = _to_core_input(
        _ag_ui_input(
            [{"id": "u1", "role": "user", "content": "hi"}],
            forwarded={"metadata": {"tenant": "acme"}},
        )
    )

    assert core.model_selection is None
    assert core.metadata == {"tenant": "acme"}


def test_to_core_input_rejects_non_object_model_selection() -> None:
    """modelSelection이 객체가 아니면 typed run selection으로 해석하지 않는다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": "openai:gpt"},
            )
        )


def test_to_core_input_allows_partial_model_selection() -> None:
    """modelSelection의 optional field는 생략 가능하다."""
    core = _to_core_input(
        _ag_ui_input(
            [{"id": "u1", "role": "user", "content": "hi"}],
            forwarded={"modelSelection": {"provider": "openai"}},
        )
    )

    assert core.model_selection is not None
    assert core.model_selection.provider == "openai"
    assert core.model_selection.model is None
    assert core.model_selection.metadata == {}


def test_to_core_input_rejects_blank_model_selection_text() -> None:
    """modelSelection 문자열 필드는 공백일 수 없다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": {"provider": " "}},
            )
        )


def test_to_core_input_rejects_non_object_run_metadata() -> None:
    """forwardedProps.metadata는 JSON object여야 한다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"metadata": "tenant=acme"},
            )
        )


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


def test_to_core_input_allows_approval_only_resume() -> None:
    """resume approval만 있는 입력은 user message 없이도 코어 resume으로 매핑된다."""
    core = _to_core_input(
        _ag_ui_input(
            [
                {
                    "id": "tool-1",
                    "role": "tool",
                    "content": (
                        '{"request_id":"approval:run-1:note.write",'
                        '"decision":"approve"}'
                    ),
                    "toolCallId": "approval:run-1:note.write",
                }
            ]
        )
    )

    assert core.instruction == RESUME_APPROVAL_INSTRUCTION
    assert core.resume is True


def test_inbound_run_pairs_raw_and_core_input() -> None:
    """inbound_run은 raw AG-UI 입력과 neutral RunAgentInput을 함께 보존한다."""
    ag_ui_input = _ag_ui_input([{"id": "u1", "role": "user", "content": "hello"}])

    inbound = inbound_run(ag_ui_input)

    assert inbound.ag_ui_input is ag_ui_input
    assert inbound.core_input.instruction == "hello"


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
