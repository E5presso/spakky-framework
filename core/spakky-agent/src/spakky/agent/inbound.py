"""Inbound run contract consumed by the framework-owned agent runner.

ADR-0013 §1 hands the execution loop to the framework runner. A caller (an
inbound adapter today, an AG-UI/A2A protocol adapter later) hands the runner a
``RunAgentInput`` describing one run: which durable run to correlate against, the
user instruction that seeds the model request, and whether the run resumes a
paused/interrupted execution (ADR-0013 §5 HITL resume / restart recovery).

A stateless caller may also carry the prior transcript inline through
``message_history`` (ADR-0013 §6 client-injected history, pydantic-ai
``message_history`` precedent). When it is empty and a ``TaskStore`` is wired,
the runner instead loads the server-persisted transcript by
``effective_conversation_id`` — the two multi-turn paths are mutually exclusive
per run, never merged.

Approval decisions are **not** carried here. The unified pause -> approval
request -> resume flow (ADR-0013 §5) delivers a decision through the durable
signal repository, not through this input, so the runner polls the signal queue
non-blockingly rather than reading a decision off the inbound contract.
"""

from dataclasses import dataclass, field

from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import ModelMessage
from spakky.agent.types import JsonObject


@dataclass(frozen=True, slots=True)
class RunAgentInput:
    """Inbound contract for one framework-owned agent run."""

    state_id: str
    instruction: str
    conversation_id: str | None = None
    parent_run_id: str | None = None
    resume: bool = False
    message_history: tuple[ModelMessage, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject inbound input that cannot correlate a run or seed a request."""
        if not self.state_id.strip():
            raise AgentDefinitionError("Run agent input state id cannot be blank")
        if not self.instruction.strip():
            raise AgentDefinitionError("Run agent input instruction cannot be blank")
        if self.conversation_id is not None and not self.conversation_id.strip():
            raise AgentDefinitionError(
                "Run agent input conversation id cannot be blank"
            )
        if self.parent_run_id is not None and not self.parent_run_id.strip():
            raise AgentDefinitionError("Run agent input parent run id cannot be blank")

    @property
    def effective_conversation_id(self) -> str:
        """Return the multi-turn thread id, defaulting to the run id.

        ADR-0013 §3 attribution requires a conversation id on every event. A
        single-turn caller may omit it, in which case the run id identifies the
        (degenerate) one-turn conversation.
        """
        return self.conversation_id or self.state_id
