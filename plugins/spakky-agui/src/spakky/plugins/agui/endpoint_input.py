"""AG-UI inbound request mapping shared by HTTP, WebSocket, and drivers."""

from dataclasses import dataclass

from ag_ui.core import RunAgentInput as AgUiRunAgentInput

from spakky.agent.inbound import RunAgentInput

from spakky.plugins.agui.error import AgUiRunResolutionError
from spakky.plugins.agui.hitl import carries_approval_decision

RESUME_APPROVAL_INSTRUCTION = "Resume the pending approval decision."
"""Instruction seed used when an AG-UI resume frame carries no user text."""


@dataclass(frozen=True, slots=True)
class AgUiInboundRun:
    """AG-UI input paired with the neutral core run input."""

    ag_ui_input: AgUiRunAgentInput
    core_input: RunAgentInput


def to_core_input(ag_ui_input: AgUiRunAgentInput) -> RunAgentInput:
    """Map an AG-UI run input onto the neutral core run input."""
    resume = carries_approval_decision(ag_ui_input)
    return RunAgentInput(
        state_id=ag_ui_input.run_id,
        instruction=_instruction_for(ag_ui_input, resume),
        conversation_id=ag_ui_input.thread_id,
        parent_run_id=ag_ui_input.parent_run_id,
        resume=resume,
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
