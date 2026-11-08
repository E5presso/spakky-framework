"""Persistence ports for durable agent state, signal, and evidence."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from spakky.agent.error import AgentEvidenceOriginQueryUnsupportedError
from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentState, AgentStatus


class IAgentStateRepository(ABC):
    """Materialized state repository for long-running agent executions."""

    @abstractmethod
    def get(self, state_id: str) -> AgentState:
        """Return a persisted agent state by id."""
        ...

    @abstractmethod
    def get_or_none(self, state_id: str) -> AgentState | None:
        """Return a persisted agent state by id, or None when absent."""
        ...

    @abstractmethod
    def save(self, state: AgentState) -> AgentState:
        """Persist the materialized state and return the saved snapshot."""
        ...

    @abstractmethod
    def list_by_status(self, status: AgentStatus) -> Sequence[AgentState]:
        """Return states matching an externally observable lifecycle status."""
        ...

    @abstractmethod
    def list_resume_candidates(self) -> Sequence[AgentState]:
        """Return active or interrupted states that may resume after restart."""
        ...


class IAgentSignalRepository(ABC):
    """Durable inbound queue repository for agent signals."""

    @abstractmethod
    def append(self, signal: AgentSignal) -> AgentSignal:
        """Append a signal to the inbound queue and return the stored entry."""
        ...

    @abstractmethod
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        """Return unconsumed signals for an agent state in append/queue order."""
        ...

    @abstractmethod
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        """Mark one queued signal as consumed after a non-blocking poll."""
        ...


class IAgentEvidenceRepository(ABC):
    """Append-only evidence repository exposed to agent-facing code."""

    @abstractmethod
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        """Append immutable evidence and return the stored artifact."""
        ...

    @abstractmethod
    def get(self, evidence_id: str) -> AgentEvidence:
        """Return one evidence artifact by id."""
        ...

    @abstractmethod
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        """Return evidence artifacts captured for an agent state."""
        ...

    @abstractmethod
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        """Return evidence artifacts associated with a context manifest."""
        ...

    def count_by_state(self, state_id: str) -> int:
        """Return how many evidence artifacts an agent state has.

        Durable stores override this with a count query so appending evidence
        does not read every earlier artifact of the run.
        """
        return len(self.list_by_state(state_id))

    def has_step_evidence(
        self,
        state_id: str,
        kind: AgentEvidenceKind,
        model_step: int,
        digest: str,
    ) -> bool:
        """Return whether one step-scoped context artifact was already recorded."""
        return any(
            item.kind == kind
            and item.model_step == model_step
            and item.digest == digest
            for item in self.list_by_state(state_id)
        )

    def list_by_origin_ref(self, origin_ref: str) -> Sequence[AgentEvidence]:
        """Return context evidence whose model context used ``origin_ref``.

        Stores without an origin index cannot answer this query.
        """
        raise AgentEvidenceOriginQueryUnsupportedError()
