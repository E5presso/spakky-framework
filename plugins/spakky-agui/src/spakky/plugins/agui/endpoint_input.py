"""AG-UI inbound request mapping shared by HTTP, WebSocket, and drivers."""

from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ag_ui.core import (
    AudioInputContent,
    BinaryInputContent,
    DocumentInputContent,
    ImageInputContent,
    InputContentDataSource,
    InputContentUrlSource,
    RunAgentInput as AgUiRunAgentInput,
    TextInputContent,
    VideoInputContent,
)

from spakky.agent import (
    AudioPart,
    AgentDefinitionError,
    DEFAULT_MEDIA_SAFETY_LIMITS,
    DocumentPart,
    ImagePart,
    JsonObject,
    JsonValue,
    ModelSelection,
    RunAgentInput,
    VideoPart,
)

from spakky.plugins.agui.error import AgUiRunResolutionError
from spakky.plugins.agui.hitl import carries_approval_decision

RESUME_APPROVAL_INSTRUCTION = "Resume the pending approval decision."
"""Instruction seed used when an AG-UI resume frame carries no user text."""

MODEL_SELECTION_FORWARDED_KEY = "modelSelection"
"""forwardedProps key carrying a run-scoped model catalog reference."""

MODEL_REF_SELECTION_KEY = "modelRef"
"""Canonical modelSelection key carrying the opaque model catalog reference."""

RUN_METADATA_FORWARDED_KEY = "metadata"
"""forwardedProps key carrying extra core RunAgentInput metadata."""

MCP_FORWARDED_KEY = "mcp"
"""forwardedProps key carrying runtime MCP server selectors."""


@dataclass(frozen=True, slots=True)
class AgUiInboundRun:
    """AG-UI input paired with the neutral core run input."""

    ag_ui_input: AgUiRunAgentInput
    core_input: RunAgentInput


type _Attachment = ImagePart | AudioPart | VideoPart | DocumentPart


@dataclass(frozen=True, slots=True)
class _UserInput:
    instruction: str
    attachments: tuple[_Attachment, ...] = ()


def to_core_input(ag_ui_input: AgUiRunAgentInput) -> RunAgentInput:
    """Map an AG-UI run input onto the neutral core run input."""
    resume = carries_approval_decision(ag_ui_input)
    forwarded = _forwarded_props(ag_ui_input)
    user_input = _user_input_for(ag_ui_input, resume)
    return RunAgentInput(
        state_id=ag_ui_input.run_id,
        instruction=user_input.instruction,
        conversation_id=ag_ui_input.thread_id,
        parent_run_id=ag_ui_input.parent_run_id,
        resume=resume,
        attachments=user_input.attachments,
        model_selection=_model_selection_from_forwarded(forwarded),
        metadata=_metadata_from_forwarded(forwarded),
    )


def inbound_run(ag_ui_input: AgUiRunAgentInput) -> AgUiInboundRun:
    """Return the raw AG-UI input and its mapped core run input."""
    return AgUiInboundRun(
        ag_ui_input=ag_ui_input,
        core_input=to_core_input(ag_ui_input),
    )


def _last_user_input(ag_ui_input: AgUiRunAgentInput) -> _UserInput:
    """Return the latest user text and every typed media attachment."""
    for message in reversed(ag_ui_input.messages):
        if message.role != "user":
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
            return _UserInput(content)
        if isinstance(content, str):
            raise AgUiRunResolutionError("AG-UI user message text cannot be blank")
        texts: list[str] = []
        attachments: list[_Attachment] = []
        for part in content:
            if isinstance(part, TextInputContent):
                if part.text.strip():
                    texts.append(part.text)
                continue
            if len(attachments) >= DEFAULT_MEDIA_SAFETY_LIMITS.max_media_parts:
                raise AgUiRunResolutionError("AG-UI message has too many media parts")
            attachments.append(_attachment(part, message.id))
            total_inline_bytes = sum(
                0 if attachment.size is None else attachment.size
                for attachment in attachments
            )
            if total_inline_bytes > DEFAULT_MEDIA_SAFETY_LIMITS.max_inline_bytes:
                raise AgUiRunResolutionError(
                    "AG-UI message exceeds the total inline media limit"
                )
        instruction = "\n".join(texts)
        if not instruction.strip():
            raise AgUiRunResolutionError(
                "AG-UI multimodal user message requires a text instruction"
            )
        return _UserInput(instruction, tuple(attachments))
    raise AgUiRunResolutionError


def _user_input_for(ag_ui_input: AgUiRunAgentInput, resume: bool) -> _UserInput:
    """Return core user input while allowing approval-only resume frames."""
    if resume and not any(message.role == "user" for message in ag_ui_input.messages):
        return _UserInput(RESUME_APPROVAL_INSTRUCTION)
    return _last_user_input(ag_ui_input)


def _attachment(part: object, message_id: str) -> _Attachment:
    if isinstance(part, BinaryInputContent):
        raise AgUiRunResolutionError("AG-UI deprecated binary content is not accepted")
    media_class: type[ImagePart | AudioPart | VideoPart | DocumentPart]
    if isinstance(part, ImageInputContent):
        media_class = ImagePart
    elif isinstance(part, AudioInputContent):
        media_class = AudioPart
    elif isinstance(part, VideoInputContent):
        media_class = VideoPart
    elif isinstance(part, DocumentInputContent):
        media_class = DocumentPart
    else:
        raise AgUiRunResolutionError("AG-UI user content part is unsupported")
    source = part.source
    provenance = f"ag-ui:{message_id}"
    if isinstance(source, InputContentUrlSource):
        if source.mime_type is None:
            raise AgUiRunResolutionError("AG-UI media URL requires mimeType")
        try:
            return media_class.from_uri(
                source.value,
                media_type=source.mime_type,
                source=provenance,
            )
        except AgentDefinitionError as error:
            raise AgUiRunResolutionError("AG-UI media URL is invalid") from error
    if not isinstance(source, InputContentDataSource):
        raise AgUiRunResolutionError("AG-UI media source is invalid")
    max_encoded_size = ((DEFAULT_MEDIA_SAFETY_LIMITS.max_inline_bytes + 2) // 3) * 4
    if len(source.value) > max_encoded_size:
        raise AgUiRunResolutionError("AG-UI inline media exceeds its encoded limit")
    try:
        data = b64decode(source.value, validate=True)
        return media_class.from_bytes(
            data,
            media_type=source.mime_type,
            source=provenance,
        )
    except (Base64Error, ValueError, AgentDefinitionError) as error:
        raise AgUiRunResolutionError("AG-UI media data is invalid") from error


def _forwarded_props(
    ag_ui_input: AgUiRunAgentInput,
) -> Mapping[str, object] | None:
    """Return forwardedProps as a mapping when the AG-UI client supplied one."""
    if ag_ui_input.forwarded_props is None:
        return None
    if not isinstance(ag_ui_input.forwarded_props, Mapping):
        raise AgUiRunResolutionError("AG-UI forwardedProps must be an object")
    return cast(Mapping[str, object], ag_ui_input.forwarded_props)


def _model_selection_from_forwarded(
    forwarded: Mapping[str, object] | None,
) -> ModelSelection | None:
    """Decode forwardedProps.modelSelection into the typed run selector."""
    if forwarded is None:
        return None
    if MODEL_SELECTION_FORWARDED_KEY not in forwarded:
        return None
    value = forwarded[MODEL_SELECTION_FORWARDED_KEY]
    if not isinstance(value, Mapping):
        raise AgUiRunResolutionError("AG-UI modelSelection must be an object")
    selection = cast(Mapping[str, object], value)
    if set(selection) != {MODEL_REF_SELECTION_KEY}:
        raise AgUiRunResolutionError(
            "AG-UI modelSelection must contain exactly modelRef"
        )
    model_ref = selection[MODEL_REF_SELECTION_KEY]
    if not isinstance(model_ref, str) or not model_ref.strip():
        raise AgUiRunResolutionError("AG-UI modelSelection.modelRef is invalid")
    return ModelSelection(model_ref=model_ref)


def _metadata_from_forwarded(
    forwarded: Mapping[str, object] | None,
) -> JsonObject:
    """Promote whitelisted forwardedProps fields into core run metadata."""
    metadata: dict[str, JsonValue] = {}
    if forwarded is None:
        return metadata
    run_metadata = forwarded.get(RUN_METADATA_FORWARDED_KEY)
    if run_metadata is not None:
        metadata.update(_json_object(run_metadata, "metadata"))
    mcp = forwarded.get(MCP_FORWARDED_KEY)
    if mcp is not None:
        metadata[MCP_FORWARDED_KEY] = _json_object(mcp, MCP_FORWARDED_KEY)
    return metadata


def _json_object(value: object, field: str) -> JsonObject:
    """Decode a JSON object supplied by forwardedProps."""
    if not isinstance(value, Mapping):
        raise AgUiRunResolutionError(f"AG-UI forwardedProps.{field} must be an object")
    return {
        key: cast(JsonValue, item)
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str)
    }
