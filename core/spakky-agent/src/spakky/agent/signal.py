"""Agent signal contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.execution import AgentSignalKind
from spakky.agent.types import JsonObject


class ApprovalDecision(StrEnum):
    """Human-in-the-loop approval outcomes."""

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    DEFER = "defer"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class AgentSignal:
    """Inbound stimulus appended for an agent execution."""

    id: str
    agent_state_id: str
    kind: AgentSignalKind
    payload: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
