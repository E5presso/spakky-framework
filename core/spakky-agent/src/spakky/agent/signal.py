"""Agent signal contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from spakky.agent.types import JsonObject


class AgentSignalKind(StrEnum):
    """Inbound stimulus kinds that an agent may accept while running."""

    USER_MESSAGE = "user_message"
    APPROVAL_DECISION = "approval_decision"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    STEERING_INSTRUCTION = "steering_instruction"
    EXTERNAL_EVENT = "external_event"
    SCHEDULER_WAKE_UP = "scheduler_wake_up"


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


class AgentSteeringUpdate(BaseModel):
    """Revisioned input; provisional observations grant no tool/final authority.

    input_id is caller-owned and scoped to a conversation/utterance. Withdrawal
    removes that input while retaining its revision tombstone for idempotence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    input_id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    content: str
    final: bool
    withdrawn: bool = False
    retain: bool = False
