"""Tests for the AG-UI -> core RunAgentInput mapping at the endpoint boundary."""

from base64 import b64encode
from collections.abc import AsyncIterator
from typing import cast

from ag_ui.core import (
    ImageInputContent,
    RunAgentInput as AgUiRunAgentInput,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch, mark, raises

from spakky.agent import (
    AudioPart,
    DocumentPart,
    ImagePart,
    MediaSafetyLimits,
    VideoPart,
)
from spakky.agent.inbound import RunAgentInput
from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import add_agui_endpoint, _to_core_input
from spakky.plugins.agui import endpoint_input as endpoint_input_module
from spakky.plugins.agui.endpoint_input import (
    RESUME_APPROVAL_INSTRUCTION,
    _attachment,
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
                "modelSelection": {"modelRef": "support/primary"},
                "mcp": {"servers": ["github"]},
                "metadata": {"tenant": "acme"},
            },
        )
    )

    assert core.model_selection is not None
    assert core.model_selection.model_ref == "support/primary"
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


def test_to_core_input_allows_mcp_without_run_metadata() -> None:
    """run metadata 없이 mcp만 전달해도 MCP selector를 승격한다."""
    core = _to_core_input(
        _ag_ui_input(
            [{"id": "u1", "role": "user", "content": "hi"}],
            forwarded={"mcp": {"servers": ["github"]}},
        )
    )

    assert core.metadata == {"mcp": {"servers": ["github"]}}


@mark.parametrize("selection", ["openai:gpt", None, ["support/primary"]])
def test_to_core_input_rejects_non_object_model_selection(selection: object) -> None:
    """modelSelection이 객체가 아니면 typed run selection으로 해석하지 않는다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": selection},
            )
        )


def test_to_core_input_rejects_model_selection_without_model_ref() -> None:
    """modelSelection object가 있으면 modelRef를 반드시 포함해야 한다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": {}},
            )
        )


@mark.parametrize("model_ref", ["", " ", 1, None])
def test_to_core_input_rejects_invalid_model_ref(model_ref: object) -> None:
    """modelRef는 nonblank string이어야 한다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": {"modelRef": model_ref}},
            )
        )


@mark.parametrize(
    "selection",
    [
        {"provider": "openrouter"},
        {"model": "anthropic/claude"},
        {"profile": "support"},
        {"metadata": {"tier": "paid"}},
        {"unknown": "value"},
        {"model_ref": "support/primary"},
        {"modelRef": "support/primary", "provider": "openrouter"},
        {"modelRef": "support/primary", "unknown": "value"},
    ],
)
def test_to_core_input_rejects_noncanonical_model_selection_keys(
    selection: dict[str, object],
) -> None:
    """modelSelection은 modelRef 외의 legacy 또는 unknown key를 거부한다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [{"id": "u1", "role": "user", "content": "hi"}],
                forwarded={"modelSelection": selection},
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


def test_to_core_input_maps_latest_multimodal_user_message() -> None:
    """Latest AG-UI text and typed media sources become ordered core attachments."""
    audio = b"audio-bytes"
    core = _to_core_input(
        _ag_ui_input(
            [
                {"id": "u1", "role": "user", "content": "earlier text"},
                {
                    "id": "u2",
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "inspect"},
                        {"type": "text", "text": "these files"},
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "value": "https://assets.example.test/image.png",
                                "mimeType": "image/png",
                            },
                        },
                        {
                            "type": "audio",
                            "source": {
                                "type": "data",
                                "value": b64encode(audio).decode("ascii"),
                                "mimeType": "audio/mpeg",
                            },
                        },
                        {
                            "type": "video",
                            "source": {
                                "type": "url",
                                "value": "https://assets.example.test/video.mp4",
                                "mimeType": "video/mp4",
                            },
                        },
                        {
                            "type": "document",
                            "source": {
                                "type": "url",
                                "value": "https://assets.example.test/report.pdf",
                                "mimeType": "application/pdf",
                            },
                        },
                    ],
                },
            ]
        )
    )

    assert core.instruction == "inspect\nthese files"
    assert core.attachments == (
        ImagePart.from_uri(
            "https://assets.example.test/image.png",
            media_type="image/png",
            source="ag-ui:u2",
        ),
        AudioPart.from_bytes(
            audio,
            media_type="audio/mpeg",
            source="ag-ui:u2",
        ),
        VideoPart.from_uri(
            "https://assets.example.test/video.mp4",
            media_type="video/mp4",
            source="ag-ui:u2",
        ),
        DocumentPart.from_uri(
            "https://assets.example.test/report.pdf",
            media_type="application/pdf",
            source="ag-ui:u2",
        ),
    )


@mark.parametrize(
    "content",
    [
        [
            {"type": "text", "text": "inspect"},
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "value": "https://assets.example.test/image.png",
                },
            },
        ],
        [
            {"type": "text", "text": "inspect"},
            {
                "type": "audio",
                "source": {
                    "type": "data",
                    "value": "not-base64",
                    "mimeType": "audio/mpeg",
                },
            },
        ],
        [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "value": "https://assets.example.test/image.png",
                    "mimeType": "image/png",
                },
            },
        ],
        [
            {
                "type": "binary",
                "mimeType": "image/png",
                "url": "https://assets.example.test/image.png",
            },
            {"type": "text", "text": "inspect"},
        ],
    ],
)
def test_to_core_input_rejects_invalid_multimodal_content(
    content: list[dict[str, object]],
) -> None:
    """Missing MIME, invalid base64, media-only, and deprecated binary fail loud."""
    with raises(AgUiRunResolutionError):
        _to_core_input(_ag_ui_input([{"id": "u1", "role": "user", "content": content}]))


def test_to_core_input_without_user_message_raises() -> None:
    """user 메시지가 없으면 AgUiRunResolutionError를 던진다."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input([{"id": "a1", "role": "assistant", "content": "ack"}])
        )


def test_to_core_input_rejects_blank_plain_user_message() -> None:
    """A blank latest plain user message cannot fall back to older text."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [
                    {"id": "old", "role": "user", "content": "older"},
                    {"id": "blank", "role": "user", "content": " "},
                ]
            )
        )


def test_to_core_input_ignores_blank_text_fragment_inside_valid_message() -> None:
    """Blank fragments are omitted when another fragment supplies instruction text."""
    core = _to_core_input(
        _ag_ui_input(
            [
                {
                    "id": "u1",
                    "role": "user",
                    "content": [
                        {"type": "text", "text": " "},
                        {"type": "text", "text": "inspect"},
                    ],
                }
            ]
        )
    )

    assert core.instruction == "inspect"


def test_attachment_defensive_boundary_rejects_unknown_part_or_source() -> None:
    """Type-corrupted AG-UI content never reaches core media factories."""
    with raises(AgUiRunResolutionError):
        _attachment(object(), "u1")
    corrupted = ImageInputContent.model_construct(source=object())
    with raises(AgUiRunResolutionError):
        _attachment(corrupted, "u1")


def test_to_core_input_rejects_disallowed_remote_media_uri() -> None:
    """Core URI safety errors are normalized at the AG-UI boundary."""
    with raises(AgUiRunResolutionError):
        _to_core_input(
            _ag_ui_input(
                [
                    {
                        "id": "u1",
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "inspect"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "value": "file:///tmp/private.png",
                                    "mimeType": "image/png",
                                },
                            },
                        ],
                    }
                ]
            )
        )


def test_to_core_input_enforces_total_attachment_count() -> None:
    """Many URI parts cannot bypass the message-level attachment bound."""
    content: list[dict[str, object]] = [{"type": "text", "text": "inspect"}]
    content.extend(
        {
            "type": "image",
            "source": {
                "type": "url",
                "value": f"https://assets.example.test/{index}.png",
                "mimeType": "image/png",
            },
        }
        for index in range(17)
    )

    with raises(AgUiRunResolutionError, match="too many"):
        _to_core_input(_ag_ui_input([{"id": "u1", "role": "user", "content": content}]))


def test_to_core_input_enforces_encoded_and_total_inline_budget(
    monkeypatch: MonkeyPatch,
) -> None:
    """Encoded input is bounded before decode and accumulated after each part."""
    limits = MediaSafetyLimits(max_inline_bytes=3, max_media_parts=4)
    monkeypatch.setattr(
        endpoint_input_module,
        "DEFAULT_MEDIA_SAFETY_LIMITS",
        limits,
    )
    oversized = [
        {"type": "text", "text": "inspect"},
        {
            "type": "image",
            "source": {
                "type": "data",
                "value": "A" * 8,
                "mimeType": "image/png",
            },
        },
    ]
    with raises(AgUiRunResolutionError, match="encoded"):
        _to_core_input(
            _ag_ui_input([{"id": "u1", "role": "user", "content": oversized}])
        )

    encoded = b64encode(b"ab").decode("ascii")
    accumulated = [
        {"type": "text", "text": "inspect"},
        *(
            {
                "type": "image",
                "source": {
                    "type": "data",
                    "value": encoded,
                    "mimeType": "image/png",
                },
            }
            for _ in range(2)
        ),
    ]
    with raises(AgUiRunResolutionError, match="total inline"):
        _to_core_input(
            _ag_ui_input([{"id": "u1", "role": "user", "content": accumulated}])
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
