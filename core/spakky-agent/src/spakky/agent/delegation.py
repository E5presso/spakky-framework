"""Agent-to-agent delegation contracts."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.types import JsonObject, JsonValue
from spakky.agent.yield_ import AgentYield, AgentYieldKind, Evidence


class DelegationReturnPolicy(StrEnum):
    """How a child agent result should be projected back to the parent."""

    SUMMARY = "summary"
    EVIDENCE_REFS = "evidence_refs"
    SUMMARY_AND_EVIDENCE = "summary_and_evidence"
    FINAL_OUTPUT = "final_output"


@dataclass(frozen=True, slots=True)
class AgentDelegateTarget:
    """First-class delegate target represented by another @Agent component."""

    agent_type: str
    agent_name: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject delegate targets that cannot identify an agent component."""
        if not self.agent_type.strip():
            raise AgentDefinitionError("Delegate target agent type cannot be blank")
        if self.agent_name is not None and not self.agent_name.strip():
            raise AgentDefinitionError("Delegate target agent name cannot be blank")


@dataclass(frozen=True, slots=True)
class DelegationBudget:
    """Budget metadata attached to a delegation packet."""

    max_steps: int | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    deadline_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject delegation budgets that cannot be enforced consistently."""
        if self.max_steps is not None and self.max_steps <= 0:
            raise AgentDefinitionError("Delegation max steps must be positive")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise AgentDefinitionError("Delegation max tokens must be positive")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Delegation timeout must be positive")


@dataclass(frozen=True, slots=True)
class DelegationContextSlice:
    """Minimal parent context projected for a child agent."""

    summary: str | None = None
    evidence_refs: tuple[str, ...] = ()
    manifest_ref: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelegationExpectedOutput:
    """Expected child output description and optional JSON schema."""

    description: str | None = None
    schema: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelegationPacket:
    """Task packet passed from a parent agent to a delegate agent."""

    id: str
    parent_agent_state_id: str
    target: AgentDelegateTarget
    task: JsonObject
    context: DelegationContextSlice = field(default_factory=DelegationContextSlice)
    constraints: tuple[str, ...] = ()
    expected_output: DelegationExpectedOutput = field(
        default_factory=DelegationExpectedOutput,
    )
    budget: DelegationBudget = field(default_factory=DelegationBudget)
    allowed_capabilities: tuple[str, ...] = ()
    return_policy: DelegationReturnPolicy = DelegationReturnPolicy.SUMMARY_AND_EVIDENCE
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject delegation packets without parent linkage or task identity."""
        if not self.id.strip():
            raise AgentDefinitionError("Delegation id cannot be blank")
        if not self.parent_agent_state_id.strip():
            raise AgentDefinitionError("Delegation parent state id cannot be blank")


@dataclass(frozen=True, slots=True)
class DelegationResult:
    """Child agent result projected back to the parent execution."""

    id: str
    packet_id: str
    target: AgentDelegateTarget
    summary: str
    output: JsonValue = None
    evidence_refs: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Reject delegated results that cannot be linked to a packet."""
        if not self.id.strip():
            raise AgentDefinitionError("Delegation result id cannot be blank")
        if not self.packet_id.strip():
            raise AgentDefinitionError("Delegation result packet id cannot be blank")
        if not self.summary.strip():
            raise AgentDefinitionError("Delegation result summary cannot be blank")

    def to_parent_evidence(
        self,
        *,
        evidence_id: str,
        parent_agent_state_id: str,
    ) -> AgentEvidence:
        """Represent a delegated result as append-only parent evidence."""
        payload: dict[str, JsonValue] = {
            "delegation_id": self.id,
            "packet_id": self.packet_id,
            "target_agent_type": self.target.agent_type,
            "evidence_refs": self.evidence_refs,
            "metadata": self.metadata,
        }
        if self.target.agent_name is not None:
            payload["target_agent_name"] = self.target.agent_name
        if self.output is not None:
            payload["output"] = self.output
        return AgentEvidence(
            id=evidence_id,
            agent_state_id=parent_agent_state_id,
            kind=AgentEvidenceKind.DELEGATION,
            payload=payload,
            summary=self.summary,
            created_at=self.created_at,
        )

    def to_parent_yield(
        self,
        *,
        evidence_id: str,
        parent_agent_state_id: str,
    ) -> AgentYield[Evidence]:
        """Expose the delegated result on the parent's AgentYield stream."""
        evidence = self.to_parent_evidence(
            evidence_id=evidence_id,
            parent_agent_state_id=parent_agent_state_id,
        )
        return AgentYield(
            kind=AgentYieldKind.EVIDENCE,
            payload=Evidence(
                evidence=evidence,
                metadata={"delegation_id": self.id, "packet_id": self.packet_id},
            ),
        )


class IAgentDelegate(ABC):
    """Execution hook that runs a delegation packet against a delegate target."""

    @abstractmethod
    def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        """Execute delegation without prescribing spawn topology or transport."""
