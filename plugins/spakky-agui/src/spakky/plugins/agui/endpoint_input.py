"""AG-UI inbound request mapping shared by HTTP, WebSocket, and drivers."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ag_ui.core import RunAgentInput as AgUiRunAgentInput

from spakky.agent import JsonObject, JsonValue, ModelSelection, RunAgentInput

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


def to_core_input(ag_ui_input: AgUiRunAgentInput) -> RunAgentInput:
    """Map an AG-UI run input onto the neutral core run input."""
    resume = carries_approval_decision(ag_ui_input)
    forwarded = _forwarded_props(ag_ui_input)
    return RunAgentInput(
        state_id=ag_ui_input.run_id,
        instruction=_instruction_for(ag_ui_input, resume),
        conversation_id=ag_ui_input.thread_id,
        parent_run_id=ag_ui_input.parent_run_id,
        resume=resume,
        model_selection=_model_selection_from_forwarded(forwarded),
        metadata=_metadata_from_forwarded(forwarded),
    )


def inbound_run(ag_ui_input: AgUiRunAgentInput) -> AgUiInboundRun:
    """Return the raw AG-UI input and its mapped core run input."""
    return AgUiInboundRun(
        ag_ui_input=ag_ui_input,
        core_input=to_core_input(ag_ui_input),
    )


def _last_user_text(ag_ui_input: AgUiRunAgentInput) -> str:
    """Return the most recent user message text seeding the model request."""
    for message in reversed(ag_ui_input.messages):
        if message.role != "user":
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
            return content
    raise AgUiRunResolutionError


def _instruction_for(ag_ui_input: AgUiRunAgentInput, resume: bool) -> str:
    """Return the core instruction while allowing approval-only resume frames."""
    try:
        return _last_user_text(ag_ui_input)
    except AgUiRunResolutionError:
        if resume:
            return RESUME_APPROVAL_INSTRUCTION
        raise


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
