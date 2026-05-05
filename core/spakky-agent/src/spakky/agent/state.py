"""Agent lifecycle state contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.types import JsonObject


class AgentStatus(StrEnum):
    """Externally observable lifecycle states for an agent execution."""

    CREATED = "created"
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStateTransition(StrEnum):
    """State transition vocabulary accepted by durable agent orchestration."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class AgentStateReason(StrEnum):
    """Structured reason that refines an externally observable lifecycle state."""

    APPROVAL_REQUIRED = "approval_required"
    USER_INTERRUPTED = "user_interrupted"
    TIMEOUT = "timeout"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLATION_CLEANUP_FAILED = "cancellation_cleanup_failed"
    RECOVERY_REQUIRES_HITL = "recovery_requires_hitl"


@dataclass(frozen=True, slots=True)
class AgentState:
    """Materialized state for a long-running agent execution."""

    id: str
    agent_type: str
    status: AgentStatus
    transition: AgentStateTransition | None = None
    reason: AgentStateReason | None = None
    current_activity: str | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    pending_signal_count: int = 0
    last_event_cursor: str | None = None
    recovery_marker: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Reject state snapshots that cannot represent a real queue count."""
        if self.pending_signal_count < 0:
            raise AgentDefinitionError("Agent pending signal count cannot be negative")
