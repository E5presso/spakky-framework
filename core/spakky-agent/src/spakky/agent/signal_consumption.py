"""Non-blocking consumption helpers for durable agent signals."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError
from spakky.agent.execution import AgentSignalKind
from spakky.agent.interfaces.repository import IAgentSignalRepository
from spakky.agent.signal import AgentSignal


class AgentSignalPollPoint(StrEnum):
    """Places where orchestration may poll durable signals without waiting."""

    SAFE_BOUNDARY = "safe_boundary"
    ACTION_BOUNDARY = "action_boundary"
    MODEL_STREAM_TICK = "model_stream_tick"
    TOOL_BOUNDARY = "tool_boundary"
    APPROVAL_BOUNDARY = "approval_boundary"
    CONFIGURED = "configured"


@dataclass(frozen=True, slots=True)
class AgentSignalConsumptionBatch:
    """Signals consumed during one non-blocking poll."""

    state_id: str
    poll_point: AgentSignalPollPoint
    signals: tuple[AgentSignal, ...]

    @property
    def consumed_count(self) -> int:
        """Return the number of signals consumed by this poll."""
        return len(self.signals)


def consume_pending_agent_signals(
    repository: IAgentSignalRepository,
    state_id: str,
    *,
    poll_point: AgentSignalPollPoint = AgentSignalPollPoint.SAFE_BOUNDARY,
    accepted_signals: Sequence[AgentSignalKind] | None = None,
    max_signals: int | None = None,
) -> AgentSignalConsumptionBatch:
    """Consume currently pending signals without sleeping or waiting for new input.

    The repository remains responsible for durable queue ordering. This helper
    consumes only the eligible prefix of the pending queue so later signals never
    overtake an earlier unaccepted signal.
    """
    if not state_id.strip():
        raise AgentDefinitionError("Agent signal state id cannot be blank")
    if max_signals is not None and max_signals <= 0:
        raise AgentDefinitionError("Agent signal max_signals must be positive")

    accepted = frozenset(accepted_signals) if accepted_signals is not None else None
    pending = tuple(repository.list_pending(state_id))
    selected = _select_consumable_prefix(
        pending,
        accepted_signals=accepted,
        max_signals=max_signals,
    )
    consumed = tuple(repository.mark_consumed(signal.id) for signal in selected)

    return AgentSignalConsumptionBatch(
        state_id=state_id,
        poll_point=poll_point,
        signals=consumed,
    )


def _select_consumable_prefix(
    pending: tuple[AgentSignal, ...],
    *,
    accepted_signals: frozenset[AgentSignalKind] | None,
    max_signals: int | None,
) -> tuple[AgentSignal, ...]:
    selected: list[AgentSignal] = []
    for signal in pending:
        if max_signals is not None and len(selected) >= max_signals:
            break
        if accepted_signals is not None and signal.kind not in accepted_signals:
            break
        selected.append(signal)
    return tuple(selected)
