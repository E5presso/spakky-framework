"""Agent-to-agent delegation contracts."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from re import sub

from spakky.agent.error import AgentDefinitionError, AgentToolDispatchError
from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.event import AgentEvent
from spakky.agent.inbound import RunAgentInput
from spakky.agent.tooling import (
    AgentToolDescriptor,
    AgentToolIdentity,
    AgentToolMetadata,
    AgentToolRuntimeContext,
    AgentToolSchemaHandle,
    DataAccess,
    EvidenceCapture,
    Externality,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
)
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


@dataclass(frozen=True, slots=True)
class DelegationToolResult:
    """Model-facing result plus child neutral events from a teammate call."""

    summary: str
    output: JsonValue = None
    events: tuple[AgentEvent, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject delegated tool results without a model-facing summary."""
        if not self.summary.strip():
            raise AgentDefinitionError("Delegation tool result summary cannot be blank")

    @classmethod
    def from_result(
        cls,
        result: DelegationResult,
        *,
        events: tuple[AgentEvent, ...] = (),
    ) -> "DelegationToolResult":
        """Build a model-facing tool result from a delegation result object."""
        return cls(
            summary=result.summary,
            output=result.output,
            events=events,
            metadata={
                "delegation_id": result.id,
                "packet_id": result.packet_id,
                "target_agent_type": result.target.agent_type,
                **result.metadata,
            },
        )


class IAgentDelegate(ABC):
    """Execution hook that runs a delegation packet against a delegate target."""

    @abstractmethod
    def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        """Execute delegation without prescribing spawn topology or transport."""

    async def delegate_tool_result(
        self,
        packet: DelegationPacket,
    ) -> DelegationToolResult:
        """Execute delegation and collect the terminal result for a tool call."""
        terminal: DelegationResult | None = None
        async for item in self.delegate(packet):
            if isinstance(item.payload, DelegationResult):
                terminal = item.payload
        if terminal is None:
            raise AgentToolDispatchError("Agent delegate produced no delegation result")
        return DelegationToolResult.from_result(terminal)


def build_teammate_tool_descriptors(
    owner: type[object],
    teammates,
) -> tuple[AgentToolDescriptor, ...]:
    """Build model-callable delegation tools from an ``@Agent`` teammate spec."""
    return tuple(
        _build_teammate_tool_descriptor(owner, teammate) for teammate in teammates
    )


def _build_teammate_tool_descriptor(
    owner: type[object],
    teammate,
) -> AgentToolDescriptor:
    token = _schema_token(teammate.name)
    schema_name = f"teammate.{token}.delegate"
    return AgentToolDescriptor(
        identity=AgentToolIdentity(
            owner_module=owner.__module__,
            owner_qualname=owner.__qualname__,
            name=f"delegate_{token}",
        ),
        owner=owner,
        callable=_teammate_callable(teammate),
        schema=AgentToolSchemaHandle(
            name=schema_name,
            input_schema_name=f"{schema_name}.input",
            output_schema_name=f"{schema_name}.output",
            input_schema={
                "type": "object",
                "title": f"{schema_name}.input",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "Instruction for the delegated teammate.",
                    },
                    "task": {
                        "type": "object",
                        "description": "Structured task payload for the teammate.",
                    },
                    "context_summary": {
                        "type": "string",
                        "description": "Optional parent context summary.",
                    },
                },
                "required": ["instruction"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "title": f"{schema_name}.output",
                "properties": {
                    "summary": {"type": "string"},
                    "output": {},
                    "metadata": {"type": "object"},
                },
                "required": ["summary"],
            },
        ),
        description=f"Delegate work to teammate '{teammate.name}'.",
        metadata=AgentToolMetadata(
            effects=ToolEffects(
                data_access=DataAccess.READ_WRITE,
                externality=(
                    Externality.LOCAL
                    if teammate.pod is not None
                    else Externality.EXTERNAL
                ),
                network=teammate.card_url is not None,
            ),
            data_access=DataAccess.READ_WRITE,
            externality=(
                Externality.LOCAL if teammate.pod is not None else Externality.EXTERNAL
            ),
            idempotency=Idempotency.UNKNOWN,
            evidence=EvidenceCapture.STRUCTURED,
            approval=ToolApprovalRequirement.NOT_REQUIRED,
        ),
    )


def _teammate_callable(teammate):
    async def delegate_teammate(
        self: object,
        runtime_context: AgentToolRuntimeContext,
        instruction: str,
        task: Mapping[str, JsonValue] | None = None,
        context_summary: str | None = None,
    ) -> DelegationToolResult:
        return await _run_teammate_tool(
            self,
            runtime_context,
            teammate,
            instruction,
            task,
            context_summary,
        )

    return delegate_teammate


async def _run_teammate_tool(
    parent: object,
    runtime_context: AgentToolRuntimeContext,
    teammate,
    instruction: str,
    task: Mapping[str, JsonValue] | None,
    context_summary: str | None,
) -> DelegationToolResult:
    if not instruction.strip():
        raise AgentToolDispatchError("Teammate delegation instruction cannot be blank")
    packet = _delegation_packet(
        runtime_context, teammate, instruction, task, context_summary
    )
    if teammate.pod is not None:
        return await _delegate_local(parent, teammate, packet, runtime_context)
    delegate = _resolve_delegate(parent)
    return await delegate.delegate_tool_result(packet)


async def _delegate_local(
    parent: object,
    teammate,
    packet: DelegationPacket,
    runtime_context: AgentToolRuntimeContext,
) -> DelegationToolResult:
    from spakky.agent.runner import AgentRunner

    child = _resolve_local_teammate(parent, teammate)
    child_input = RunAgentInput(
        state_id=packet.id,
        instruction=_packet_instruction(packet),
        conversation_id=runtime_context.conversation_id,
        parent_run_id=runtime_context.state_id,
        metadata={"delegation_packet_id": packet.id, "teammate": teammate.name},
    )
    events = tuple(
        [
            event
            async for event in AgentRunner.for_agent_instance(child).run_events(
                child_input
            )
        ]
    )
    return DelegationToolResult(
        summary=f"teammate '{teammate.name}' completed",
        output={"event_count": len(events)},
        events=events,
        metadata={
            "packet_id": packet.id,
            "target_agent_type": packet.target.agent_type,
            "teammate": teammate.name,
        },
    )


def _delegation_packet(
    runtime_context: AgentToolRuntimeContext,
    teammate,
    instruction: str,
    task: Mapping[str, JsonValue] | None,
    context_summary: str | None,
) -> DelegationPacket:
    task_payload = _task_payload(instruction, task)
    return DelegationPacket(
        id=f"{runtime_context.state_id}:{runtime_context.call_id}",
        parent_agent_state_id=runtime_context.state_id,
        target=AgentDelegateTarget(
            agent_type=(
                teammate.pod.__name__
                if teammate.pod is not None
                else f"remote:{teammate.name}"
            ),
            agent_name=teammate.name,
            metadata={
                **(
                    {"card_url": teammate.card_url}
                    if teammate.card_url is not None
                    else {}
                ),
            },
        ),
        task=task_payload,
        context=DelegationContextSlice(summary=context_summary),
        metadata={"conversation_id": runtime_context.conversation_id},
    )


def _task_payload(
    instruction: str,
    task: Mapping[str, JsonValue] | None,
) -> JsonObject:
    if task is None:
        return {"instruction": instruction}
    payload: dict[str, JsonValue] = {"instruction": instruction}
    for key, value in task.items():
        if not isinstance(key, str):
            raise AgentToolDispatchError(
                "Teammate delegation task keys must be strings"
            )
        payload[key] = value
    return payload


def _packet_instruction(packet: DelegationPacket) -> str:
    instruction = packet.task.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise AgentToolDispatchError("Teammate delegation packet lacks instruction")
    return instruction


def _resolve_local_teammate(parent: object, teammate) -> object:
    matches = tuple(
        value for value in vars(parent).values() if isinstance(value, teammate.pod)
    )
    if len(matches) != 1:
        raise AgentToolDispatchError(
            "Local teammate delegation requires exactly one injected teammate pod"
        )
    return matches[0]


def _resolve_delegate(parent: object) -> IAgentDelegate:
    matches = tuple(
        value for value in vars(parent).values() if isinstance(value, IAgentDelegate)
    )
    if len(matches) != 1:
        raise AgentToolDispatchError(
            "Remote teammate delegation requires exactly one IAgentDelegate port"
        )
    return matches[0]


def _schema_token(name: str) -> str:
    token = sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    if not token:
        raise AgentDefinitionError("Agent teammate name cannot form a tool schema")
    return token
