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


class AgentSignalPriority(StrEnum):
    """Producer-assigned urgency used only for live mailbox lane routing.

    Priority is a delivery hint, not part of the durable ledger row. Replayed
    signals are applied at the first safe boundary of a starting or resuming run,
    where no in-flight work exists to interrupt.
    """

    NORMAL = "normal"
    URGENT = "urgent"


class AgentSignalLane(StrEnum):
    """Live delivery lanes of a run mailbox.

    ``CONTROL`` interrupts the in-flight model operation immediately (cancel and
    urgent revisioned steering). ``STEERING`` waits in the run mailbox until the
    next safe point, such as a finished model response or tool boundary.
    """

    CONTROL = "control"
    STEERING = "steering"


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
    priority: AgentSignalPriority = AgentSignalPriority.NORMAL

    @property
    def lane(self) -> AgentSignalLane:
        """Return the live mailbox lane selected by kind and producer priority."""
        if (
            self.kind is AgentSignalKind.CANCEL
            or self.priority is AgentSignalPriority.URGENT
        ):
            return AgentSignalLane.CONTROL
        return AgentSignalLane.STEERING


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
