"""Shared unit-test fakes for the A2A plugin.

Provides a recording ``EventQueue`` so projections can be asserted against the
real ``TaskUpdater``, plus in-memory agent repository fakes mirrored from the
spakky-agent core test doubles.
"""

from collections.abc import Sequence
from typing import override

import pytest
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.evidence import AgentEvidence
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentState, AgentStatus

type RecordedEvent = object


class RecordingEventQueue(EventQueue):
    """EventQueue test double capturing every enqueued event in order."""

    events: list[RecordedEvent]

    def __init__(self) -> None:
        self.events = []

    @override
    async def enqueue_event(self, event: RecordedEvent) -> None:
        self.events.append(event)

    def status_updates(self) -> list[TaskStatusUpdateEvent]:
        """Return only the recorded status-update events."""
        return [e for e in self.events if isinstance(e, TaskStatusUpdateEvent)]

    def artifact_updates(self) -> list[TaskArtifactUpdateEvent]:
        """Return only the recorded artifact-update events."""
        return [e for e in self.events if isinstance(e, TaskArtifactUpdateEvent)]


@pytest.fixture
def queue() -> RecordingEventQueue:
    """Provide a fresh recording event queue per test."""
    return RecordingEventQueue()


@pytest.fixture
def updater(queue: RecordingEventQueue) -> TaskUpdater:
    """Provide a TaskUpdater bound to the recording queue and a fixed task."""
    return TaskUpdater(queue, task_id="task-1", context_id="ctx-1")


class FakeStateRepository(IAgentStateRepository):
    """State repository test double mirroring the core agent test fake."""

    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    @override
    def get(self, state_id: str) -> AgentState:
        state = self._states.get(state_id)
        if state is None:
            raise AgentDefinitionError("Missing test state")
        return state

    @override
    def get_or_none(self, state_id: str) -> AgentState | None:
        return self._states.get(state_id)

    @override
    def save(self, state: AgentState) -> AgentState:
        self._states[state.id] = state
        return state

    @override
    def list_by_status(self, status: AgentStatus) -> Sequence[AgentState]:
        return tuple(s for s in self._states.values() if s.status is status)

    @override
    def list_resume_candidates(self) -> Sequence[AgentState]:
        return tuple(
            s
            for s in self._states.values()
            if s.status in (AgentStatus.ACTIVE, AgentStatus.INTERRUPTED)
        )


class FakeSignalRepository(IAgentSignalRepository):
    """Signal repository test double mirroring the core agent test fake."""

    def __init__(self, signals: Sequence[AgentSignal] = ()) -> None:
        self._signals = tuple(signals)
        self._consumed: set[str] = set()

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        self._signals = (*self._signals, signal)
        return signal

    @override
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(
            s
            for s in self._signals
            if s.agent_state_id == state_id and s.id not in self._consumed
        )

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        for signal in self._signals:
            if signal.id == signal_id:
                self._consumed.add(signal_id)
                return signal
        raise AgentDefinitionError("Missing test signal")

    def appended(self) -> tuple[AgentSignal, ...]:
        """Return every signal currently held, for append assertions."""
        return self._signals


class FakeEvidenceRepository(IAgentEvidenceRepository):
    """Evidence repository test double mirroring the core agent test fake."""

    def __init__(self) -> None:
        self._evidence: dict[str, AgentEvidence] = {}

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        self._evidence[evidence.id] = evidence
        return evidence

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise AgentDefinitionError("Missing test evidence")
        return evidence

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(a for a in self._evidence.values() if a.agent_state_id == state_id)

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        return tuple(
            a for a in self._evidence.values() if a.manifest_ref == manifest_ref
        )
