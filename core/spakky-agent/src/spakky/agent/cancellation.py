"""Cancellation lifecycle and cleanup contracts for agent execution."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.evidence import AgentEvidenceCandidate, AgentEvidenceKind
from spakky.agent.execution import AgentSignalKind
from spakky.agent.signal import AgentSignal
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.types import JsonObject, JsonValue


class AgentCancellationTargetKind(StrEnum):
    """Running execution target that can receive a cancellation cleanup hook."""

    MODEL_STREAM = "model_stream"
    TOOL_EXECUTION = "tool_execution"
    DELEGATE_EXECUTION = "delegate_execution"


class AgentCancellationCleanupStatus(StrEnum):
    """Outcome of one cancellation cleanup hook."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class AgentCancellationRequest:
    """Cancellation request passed to a model stream, tool, or delegate hook."""

    state_id: str
    signal_id: str
    target_kind: AgentCancellationTargetKind
    target_ref: str
    reason: str | None = None
    requested_by: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject requests that cannot be traced back to state/signal/target."""
        _require_non_blank(self.state_id, "Agent cancellation state id")
        _require_non_blank(self.signal_id, "Agent cancellation signal id")
        _require_non_blank(self.target_ref, "Agent cancellation target ref")
        _require_optional_non_blank(self.reason, "Agent cancellation reason")
        _require_optional_non_blank(self.requested_by, "Agent cancellation requester")

    @classmethod
    def from_signal(
        cls,
        *,
        state: AgentState,
        signal: AgentSignal,
        target_kind: AgentCancellationTargetKind,
        target_ref: str,
        metadata: JsonObject | None = None,
    ) -> "AgentCancellationRequest":
        """Build a hook request from the durable CANCEL signal payload."""
        _require_cancel_signal(signal)
        _require_signal_matches_state(state, signal)
        return cls(
            state_id=state.id,
            signal_id=signal.id,
            target_kind=target_kind,
            target_ref=target_ref,
            reason=_optional_string(signal.payload, "reason"),
            requested_by=_optional_string(signal.payload, "requested_by"),
            metadata={} if metadata is None else metadata,
        )

    def to_payload(self) -> JsonObject:
        """Serialize the request into append-only evidence metadata."""
        return {
            "state_id": self.state_id,
            "signal_id": self.signal_id,
            "target_kind": self.target_kind.value,
            "target_ref": self.target_ref,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class AgentCancellationCleanupResult:
    """Result returned by one cancellation cleanup hook."""

    target_kind: AgentCancellationTargetKind
    target_ref: str
    status: AgentCancellationCleanupStatus
    reason: str | None = None
    error_code: str | None = None
    message: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject outcomes that cannot be correlated with the cleanup target."""
        _require_non_blank(self.target_ref, "Agent cancellation cleanup target ref")
        _require_optional_non_blank(self.reason, "Agent cancellation cleanup reason")
        _require_optional_non_blank(
            self.error_code,
            "Agent cancellation cleanup error code",
        )
        _require_optional_non_blank(self.message, "Agent cancellation cleanup message")

    @classmethod
    def succeeded(
        cls,
        *,
        target_kind: AgentCancellationTargetKind,
        target_ref: str,
        reason: str | None = None,
        metadata: JsonObject | None = None,
    ) -> "AgentCancellationCleanupResult":
        """Record a cleanup hook that released its target."""
        return cls(
            target_kind=target_kind,
            target_ref=target_ref,
            status=AgentCancellationCleanupStatus.SUCCEEDED,
            reason=reason,
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def failed(
        cls,
        *,
        target_kind: AgentCancellationTargetKind,
        target_ref: str,
        error_code: str,
        message: str,
        metadata: JsonObject | None = None,
    ) -> "AgentCancellationCleanupResult":
        """Record a cleanup hook that could not release its target."""
        return cls(
            target_kind=target_kind,
            target_ref=target_ref,
            status=AgentCancellationCleanupStatus.FAILED,
            error_code=error_code,
            message=message,
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def skipped(
        cls,
        *,
        target_kind: AgentCancellationTargetKind,
        target_ref: str,
        reason: str,
        metadata: JsonObject | None = None,
    ) -> "AgentCancellationCleanupResult":
        """Record a cleanup target that was already inactive or unavailable."""
        return cls(
            target_kind=target_kind,
            target_ref=target_ref,
            status=AgentCancellationCleanupStatus.SKIPPED,
            reason=reason,
            metadata={} if metadata is None else metadata,
        )

    @property
    def failed_cleanup(self) -> bool:
        """Return whether this hook prevents a clean CANCELLED terminal state."""
        return self.status is AgentCancellationCleanupStatus.FAILED

    def to_payload(self) -> JsonObject:
        """Serialize this hook outcome into evidence/state metadata."""
        return {
            "target_kind": self.target_kind.value,
            "target_ref": self.target_ref,
            "status": self.status.value,
            "reason": self.reason,
            "error_code": self.error_code,
            "message": self.message,
            "metadata": self.metadata,
        }


type AgentCancellationCleanupCallable = Callable[
    [AgentCancellationRequest],
    Awaitable[AgentCancellationCleanupResult],
]
"""Async hook shape invoked for model stream/tool/delegate cancellation cleanup."""


@dataclass(frozen=True, slots=True)
class AgentCancellationCleanupTask:
    """One cleanup hook registered for a running cancellation target."""

    target_kind: AgentCancellationTargetKind
    target_ref: str
    cleanup: AgentCancellationCleanupCallable
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject hooks that cannot be identified in cleanup evidence."""
        _require_non_blank(self.target_ref, "Agent cancellation cleanup target ref")

    async def run(
        self,
        *,
        state: AgentState,
        signal: AgentSignal,
    ) -> AgentCancellationCleanupResult:
        """Invoke the hook and verify that it reports the same target."""
        request = AgentCancellationRequest.from_signal(
            state=state,
            signal=signal,
            target_kind=self.target_kind,
            target_ref=self.target_ref,
            metadata=self.metadata,
        )
        result = await self.cleanup(request)
        if (
            result.target_kind is not self.target_kind
            or result.target_ref != self.target_ref
        ):
            raise AgentDefinitionError(
                "Agent cancellation cleanup result target must match the task"
            )
        return result


@dataclass(frozen=True, slots=True)
class AgentCancellationCleanupReport:
    """Aggregate cleanup evidence for one CANCEL signal."""

    state_id: str
    signal_id: str
    outcomes: tuple[AgentCancellationCleanupResult, ...] = ()

    def __post_init__(self) -> None:
        """Reject reports that cannot be attached to state and signal evidence."""
        _require_non_blank(self.state_id, "Agent cancellation report state id")
        _require_non_blank(self.signal_id, "Agent cancellation report signal id")

    @property
    def cleanup_succeeded(self) -> bool:
        """Return whether all cleanup hooks completed without failure."""
        return not any(outcome.failed_cleanup for outcome in self.outcomes)

    @property
    def failed_outcomes(self) -> tuple[AgentCancellationCleanupResult, ...]:
        """Return the hook outcomes that force FAILED terminal state."""
        return tuple(outcome for outcome in self.outcomes if outcome.failed_cleanup)

    def to_payload(self) -> JsonObject:
        """Serialize the report for state metadata and evidence payloads."""
        return {
            "state_id": self.state_id,
            "signal_id": self.signal_id,
            "cleanup_succeeded": self.cleanup_succeeded,
            "outcomes": tuple(outcome.to_payload() for outcome in self.outcomes),
        }

    def to_evidence_candidate(
        self,
        *,
        summary: str | None = None,
    ) -> AgentEvidenceCandidate:
        """Represent cancellation cleanup as append-only evidence."""
        return AgentEvidenceCandidate(
            kind=AgentEvidenceKind.CANCELLATION,
            payload=self.to_payload(),
            summary=summary,
        )


async def run_agent_cancellation_cleanup(
    *,
    state: AgentState,
    signal: AgentSignal,
    tasks: Sequence[AgentCancellationCleanupTask],
) -> AgentCancellationCleanupReport:
    """Invoke model stream/tool/delegate cleanup hooks for a CANCEL signal."""
    _require_cancel_signal(signal)
    outcomes: list[AgentCancellationCleanupResult] = []
    for task in tasks:
        outcomes.append(await task.run(state=state, signal=signal))
    return AgentCancellationCleanupReport(
        state_id=state.id,
        signal_id=signal.id,
        outcomes=tuple(outcomes),
    )


def begin_agent_cancellation(
    state: AgentState,
    signal: AgentSignal,
) -> AgentState:
    """Materialize receipt of a CANCEL signal as CANCELLING state."""
    _require_cancel_signal(signal)
    _require_signal_matches_state(state, signal)
    return replace(
        state,
        status=AgentStatus.CANCELLING,
        transition=AgentStateTransition.CANCELLING,
        reason=AgentStateReason.CANCELLATION_REQUESTED,
        metadata={
            **state.metadata,
            "cancellation_signal_id": signal.id,
            "cancellation_reason": _optional_string(signal.payload, "reason"),
            "cancellation_requested_by": _optional_string(
                signal.payload,
                "requested_by",
            ),
        },
    )


def complete_agent_cancellation(
    state: AgentState,
    report: AgentCancellationCleanupReport,
) -> AgentState:
    """Resolve CANCELLING state into CANCELLED or FAILED cleanup outcome."""
    if state.id != report.state_id:
        raise AgentDefinitionError("Agent cancellation report state id mismatch")
    metadata = {**state.metadata, "cancellation_cleanup": report.to_payload()}
    if report.cleanup_succeeded:
        return replace(
            state,
            status=AgentStatus.CANCELLED,
            transition=AgentStateTransition.CANCELLED,
            reason=AgentStateReason.CANCELLATION_REQUESTED,
            metadata=metadata,
        )
    return replace(
        state,
        status=AgentStatus.FAILED,
        transition=AgentStateTransition.FAILED,
        reason=AgentStateReason.CANCELLATION_CLEANUP_FAILED,
        metadata=metadata,
    )


def _require_cancel_signal(signal: AgentSignal) -> None:
    if signal.kind is not AgentSignalKind.CANCEL:
        raise AgentDefinitionError("Agent cancellation requires a CANCEL signal")


def _require_signal_matches_state(state: AgentState, signal: AgentSignal) -> None:
    if signal.agent_state_id != state.id:
        raise AgentDefinitionError("Agent cancellation signal must belong to state")


def _optional_string(payload: JsonObject, key: str) -> str | None:
    value: JsonValue | None = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")


def _require_optional_non_blank(value: str | None, label: str) -> None:
    if value is not None and not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")
