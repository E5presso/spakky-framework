"""Agent streaming yield contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from spakky.agent.evidence import AgentEvidence
from spakky.agent.signal import ApprovalDecision
from spakky.agent.types import JsonObject, JsonValue

OutputT = TypeVar("OutputT")


class AgentYieldKind(StrEnum):
    """Canonical public vocabulary yielded by agent execution."""

    TEXT_DELTA = "text_delta"
    MESSAGE = "message"
    EVIDENCE = "evidence"
    APPROVAL = "approval"
    CHECKPOINT = "checkpoint"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class AgentYield(Generic[OutputT]):
    """Typed stream item returned from an agent execute generator."""

    kind: AgentYieldKind
    payload: OutputT


@dataclass(frozen=True, slots=True)
class TextDelta:
    """Incremental model text intended for streaming clients."""

    text: str


@dataclass(frozen=True, slots=True)
class Message:
    """Agent progress or narrative message."""

    text: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """Evidence item surfaced to the inbound adapter."""

    evidence: AgentEvidence


@dataclass(frozen=True, slots=True)
class Approval:
    """Approval request surfaced to the inbound adapter."""

    id: str
    prompt: str
    allowed_decisions: tuple[ApprovalDecision, ...]
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Action-boundary checkpoint marker surfaced to the caller."""

    marker: str
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class Final(Generic[OutputT]):
    """Final output carried by an async generator stream."""

    output: OutputT
    metadata: JsonObject


type AgentYieldPayload[OutputT] = (
    Approval | Checkpoint | Evidence | Final[OutputT] | Message | TextDelta | JsonValue
)
