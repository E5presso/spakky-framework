"""Agent streaming yield contracts."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

from spakky.agent.evidence import AgentEvidence
from spakky.agent.signal import ApprovalDecision
from spakky.agent.types import JsonObject, JsonValue

OutputT = TypeVar("OutputT")


class AgentYieldKind(StrEnum):
    """Canonical public vocabulary yielded by agent execution."""

    TOKEN = "token"
    PROGRESS = "progress"
    TOOL = "tool"
    EVIDENCE = "evidence"
    APPROVAL = "approval"
    FINAL = "final"
    ERROR = "error"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class AgentYield(Generic[OutputT]):
    """Typed stream item returned from an agent execute generator."""

    kind: AgentYieldKind
    payload: OutputT


@dataclass(frozen=True, slots=True)
class Token:
    """Incremental model token intended for streaming clients."""

    text: str
    metadata: JsonObject = field(default_factory=dict)


TextDelta = Token
"""Backward-compatible token-yield payload alias."""


@dataclass(frozen=True, slots=True)
class Progress:
    """Agent progress update intended for direct inbound adapter consumption."""

    message: str
    current_step: str | None = None
    metadata: JsonObject = field(default_factory=dict)


Message = Progress
"""Backward-compatible progress-yield payload alias."""


@dataclass(frozen=True, slots=True)
class Tool:
    """Tool call or tool result surfaced by agent execution."""

    name: str
    call_id: str | None = None
    arguments: JsonObject = field(default_factory=dict)
    result: JsonValue = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Evidence:
    """Evidence item surfaced to the inbound adapter."""

    evidence: AgentEvidence
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Approval:
    """Approval request surfaced to the inbound adapter."""

    id: str
    prompt: str
    allowed_decisions: tuple[ApprovalDecision, ...]
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class Error:
    """Recoverable or terminal execution error surfaced to the caller."""

    code: str
    message: str
    retryable: bool = False
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Cancel:
    """Cancellation acknowledgement surfaced to the caller."""

    reason: str | None = None
    requested_by: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Final(Generic[OutputT]):
    """Final output carried by a generator stream."""

    output: OutputT
    metadata: JsonObject


type AgentYieldPayload[OutputT] = (
    Approval | Cancel | Error | Evidence | Final[OutputT] | Progress | Token | Tool
)
