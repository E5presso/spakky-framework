"""Human-in-the-loop projection and decision ingestion for the AG-UI adapter.

AG-UI has no first-class approval event, so an approval request surfaces as a
*deferred tool call*: a ``TOOL_CALL_START``/``ARGS``/``END`` triple naming the
synthetic ``hitl_approval`` tool, deliberately with **no** result frame. The
client renders it, collects the human decision, and returns that decision on the
next ``RunAgentInput`` (as the deferred tool's result message, or as
``forwardedProps.approvalDecision``). ``ingest_decision`` decodes that decision
and appends it to the durable signal queue the runner polls (ADR-0013 §5), which
is the only channel the core run accepts an approval decision through.

The core ``run_events`` stream emits **no** approval event when a tool pauses
for approval — it dispatches nothing and emits no result. The pause is instead
durable: the runner saves a WAIT_FOR_APPROVAL state (status ``INTERRUPTED``,
reason ``APPROVAL_REQUIRED``) carrying the ``AgentApprovalRequest`` metadata.
``project_pending_approval`` reads that durable state after the stream ends and
rebuilds the deferred-tool frame, which is the adapter's only hook to surface a
pending approval the lossless event stream does not carry.
"""

import uuid
from collections.abc import Mapping
from json import JSONDecodeError, loads

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.core import ToolMessage

from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from spakky.agent.execution import AgentSignalKind
from spakky.agent.interfaces.repository import IAgentSignalRepository
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.state import AgentState, AgentStateReason, AgentStatus
from spakky.agent.types import JsonObject, JsonValue
from spakky.agent.yield_ import Approval

from spakky.plugins.agui.error import (
    AgUiApprovalDecodeError,
    AgUiPendingApprovalError,
)
from spakky.plugins.agui.serialization import dump_json

HITL_APPROVAL_TOOL_NAME = "hitl_approval"
"""Synthetic tool name carrying an approval request as a deferred tool call."""

APPROVAL_DECISION_FORWARDED_KEY = "approvalDecision"
"""forwardedProps key a client may use to return an approval decision."""

APPROVAL_STATE_METADATA_KEY = "approval"
"""State-metadata key under which the runner stores the approval request."""


def project_approval(
    approval: Approval,
    attribution: AgentEventAttribution,
) -> list[AgentEvent]:
    """Render an approval request as a deferred-tool frame (no result).

    The deferred call id is the approval id, so the resume tool-result message
    addresses the same call. The args carry the human-facing prompt, the allowed
    decisions, and any approval metadata the runner attached.
    """
    args: JsonObject = {
        "prompt": approval.prompt,
        "allowed_decisions": [
            decision.value for decision in approval.allowed_decisions
        ],
        **approval.metadata,
    }
    return [
        ToolCallStartEvent(
            attribution=attribution,
            call_id=approval.id,
            tool_name=HITL_APPROVAL_TOOL_NAME,
        ),
        ToolCallArgsDeltaEvent(
            attribution=attribution,
            call_id=approval.id,
            args_delta=dump_json(args),
        ),
        ToolCallEndEvent(attribution=attribution, call_id=approval.id),
    ]


def find_pending_approval(state: AgentState) -> Approval | None:
    """Reconstruct the pending approval from a durable WAIT_FOR_APPROVAL state.

    The runner saves the paused boundary as an ``INTERRUPTED`` state whose reason
    is ``APPROVAL_REQUIRED``, carrying the ``AgentApprovalRequest`` metadata under
    ``metadata["approval"]`` and the human-facing prompt in ``current_activity``.
    Returns the rebuilt approval when the state is paused for approval, otherwise
    ``None`` (the run finished or paused for some other reason).
    """
    if (
        state.status is not AgentStatus.INTERRUPTED
        or state.reason is not AgentStateReason.APPROVAL_REQUIRED
    ):
        return None
    approval_metadata = state.metadata.get(APPROVAL_STATE_METADATA_KEY)
    if not isinstance(approval_metadata, Mapping) or state.current_activity is None:
        raise AgUiPendingApprovalError
    return Approval(
        id=_require_text(approval_metadata, "id"),
        prompt=state.current_activity,
        allowed_decisions=_decode_allowed_decisions(approval_metadata),
        metadata=_approval_request_metadata(approval_metadata),
    )


def project_pending_approval(
    state: AgentState,
    attribution: AgentEventAttribution,
) -> list[AgentEvent]:
    """Project a durable pending approval into the deferred-tool request frame.

    The transport calls this after the ``run_events`` stream ends, since that
    stream emits no approval event: the pause lives only in the durable state.
    Returns an empty list when the state is not paused for approval.
    """
    approval = find_pending_approval(state)
    if approval is None:
        return []
    return project_approval(approval, attribution)


def _decode_allowed_decisions(
    approval_metadata: Mapping[str, JsonValue],
) -> tuple[ApprovalDecision, ...]:
    decisions = approval_metadata.get("allowed_decisions")
    if not isinstance(decisions, list):
        raise AgUiPendingApprovalError
    return tuple(_decode_decision(decision) for decision in decisions)


def _decode_decision(value: JsonValue) -> ApprovalDecision:
    if not isinstance(value, str):
        raise AgUiPendingApprovalError
    try:
        return ApprovalDecision(value)
    except ValueError as error:
        raise AgUiPendingApprovalError from error


def _approval_request_metadata(
    approval_metadata: Mapping[str, JsonValue],
) -> JsonObject:
    nested = approval_metadata.get("metadata")
    if not isinstance(nested, Mapping):
        raise AgUiPendingApprovalError
    return dict(nested)


def _require_text(approval_metadata: Mapping[str, JsonValue], key: str) -> str:
    value = approval_metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgUiPendingApprovalError
    return value


def ingest_decision(
    ag_ui_input: AgUiRunAgentInput,
    signals: IAgentSignalRepository,
    state_id: str,
) -> None:
    """Decode an approval decision from an AG-UI input and queue it as a signal.

    Reads the decision from the ``hitl_approval`` tool-result message when
    present, otherwise from ``forwardedProps.approvalDecision``. The decoded
    decision is appended as an ``APPROVAL_DECISION`` signal carrying the request
    id the runner correlates against, plus optional modified payload and comment.
    """
    decision_payload = _extract_decision_payload(ag_ui_input)
    request_id = decision_payload.get("request_id")
    decision_value = decision_payload.get("decision")
    if not isinstance(request_id, str) or not isinstance(decision_value, str):
        raise AgUiApprovalDecodeError
    decision = _parse_decision(decision_value)
    payload: dict[str, JsonValue] = {
        "request_id": request_id,
        "decision": decision.value,
    }
    modified_payload = decision_payload.get("modified_payload")
    if modified_payload is not None:
        payload["modified_payload"] = modified_payload
    comment = decision_payload.get("comment")
    if comment is not None:
        payload["comment"] = comment
    signals.append(
        AgentSignal(
            id=f"agui-approval:{uuid.uuid4().hex}",
            agent_state_id=state_id,
            kind=AgentSignalKind.APPROVAL_DECISION,
            payload=payload,
        )
    )


def carries_approval_decision(ag_ui_input: AgUiRunAgentInput) -> bool:
    """Return whether the AG-UI input carries an approval decision to resume on."""
    return _decision_source(ag_ui_input) is not None


def _parse_decision(value: str) -> ApprovalDecision:
    try:
        return ApprovalDecision(value)
    except ValueError as error:
        raise AgUiApprovalDecodeError from error


def _extract_decision_payload(
    ag_ui_input: AgUiRunAgentInput,
) -> Mapping[str, JsonValue]:
    payload = _decision_source(ag_ui_input)
    if payload is None:
        raise AgUiApprovalDecodeError
    return payload


def _decision_source(
    ag_ui_input: AgUiRunAgentInput,
) -> Mapping[str, JsonValue] | None:
    """Return the decision payload from a tool-result message or forwardedProps.

    A tool-result message addressed to a ``hitl_approval`` call takes priority;
    its JSON ``content`` is the decision payload. Otherwise a
    ``forwardedProps.approvalDecision`` mapping is used when present.
    """
    for message in reversed(ag_ui_input.messages):
        if not isinstance(message, ToolMessage):
            continue
        content = _decode_tool_content(message.content)
        if content is not None:
            return content
    forwarded = ag_ui_input.forwarded_props
    if isinstance(forwarded, Mapping):
        decision = forwarded.get(APPROVAL_DECISION_FORWARDED_KEY)
        if isinstance(decision, Mapping):
            return decision
    return None


def _decode_tool_content(content: str) -> Mapping[str, JsonValue] | None:
    parsed = _load_json_object(content)
    if parsed is None or "decision" not in parsed:
        return None
    return parsed


def _load_json_object(content: str) -> Mapping[str, JsonValue] | None:
    try:
        parsed = loads(content)
    except JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None
