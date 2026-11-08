"""Live per-run signal mailboxes beside the durable signal ledger.

The ``IAgentSignalRepository`` row remains the durable ledger (outbox) of every
signal. Live delivery is a separate port: a producer publishes a signal to an
``IAgentSignalPublisher`` only after its own transaction commits, and a running
agent receives it through the ``AgentRunMailbox`` it subscribed for its state.
A run replays unconsumed ledger rows once when it starts or resumes, then waits
on the mailbox instead of re-reading the ledger, so an idle run issues no
signal queries at all.

The default ``InProcessAgentSignalMailbox`` delivers inside one process. It is
safe to publish from any thread or event loop: delivery is handed to the run's
own loop with ``call_soon_threadsafe``. A cross-process transport (for example
PostgreSQL ``NOTIFY`` or Kafka) can implement ``IAgentSignalPublisher`` on the
producer side and feed received signals into the in-process mailbox.
"""

from abc import ABC, abstractmethod
from asyncio import AbstractEventLoop, Event, get_running_loop
from collections import deque
from logging import getLogger
from threading import Lock
from typing import override

from spakky.core.pod.annotations.pod import Pod

from spakky.agent.signal import AgentSignal, AgentSignalLane

logger = getLogger(__name__)


class IAgentSignalPublisher(ABC):
    """Port that delivers committed signals to live run mailboxes."""

    @abstractmethod
    def publish(self, signal: AgentSignal) -> None:
        """Deliver one signal whose ledger row is already committed.

        Implementations must be thread-safe and must not block. Publishing a
        signal for a state with no live subscriber is not an error: the ledger
        row is replayed when that state's run next starts or resumes.
        """
        ...


class IAgentSignalSubscriber(ABC):
    """Port that opens the live mailbox of one running agent state."""

    @abstractmethod
    def subscribe(self, state_id: str) -> "AgentRunMailbox":
        """Open a mailbox bound to the calling event loop for ``state_id``."""
        ...


class AgentRunMailbox:
    """Live, loop-bound inbox of one agent run with control and steering lanes.

    ``deliver`` may be called from any thread. Accepted signals are queued in
    arrival order; ``drain`` hands them to the run at its next observation.
    ``wait`` wakes on any arrival and ``wait_control`` only on a
    ``AgentSignalLane.CONTROL`` arrival, so in-flight work is interrupted only
    by cancel or urgent input while ordinary steering waits for a safe point.
    """

    _state_id: str
    _loop: AbstractEventLoop
    _owner: "InProcessAgentSignalMailbox | None"
    _queue: deque[AgentSignal]
    _arrived: Event
    _control_arrived: Event
    _closed: bool

    def __init__(
        self,
        state_id: str,
        loop: AbstractEventLoop,
        owner: "InProcessAgentSignalMailbox | None" = None,
    ) -> None:
        """Bind a mailbox to one agent state and the event loop running it."""
        self._state_id = state_id
        self._loop = loop
        self._owner = owner
        self._queue = deque()
        self._arrived = Event()
        self._control_arrived = Event()
        self._closed = False

    @property
    def state_id(self) -> str:
        """Return the agent state this mailbox receives signals for."""
        return self._state_id

    @property
    def closed(self) -> bool:
        """Return whether the run closed this mailbox."""
        return self._closed

    def deliver(self, signal: AgentSignal) -> None:
        """Hand one committed signal to the run loop from any thread.

        A producer already running on the run's own loop (for example a tool
        appending a signal) is accepted synchronously so the very next boundary
        observes it; any other thread or loop is handed over with
        ``call_soon_threadsafe``.
        """
        if self._on_own_loop():
            self._accept(signal)
            return
        try:
            self._loop.call_soon_threadsafe(self._accept, signal)
        except RuntimeError:
            # The run loop already closed; the ledger row is replayed on resume.
            logger.debug(
                "Agent signal mailbox loop closed before delivery",
                extra={"state_id": self._state_id, "signal_id": signal.id},
            )

    def drain(self) -> tuple[AgentSignal, ...]:
        """Return and clear every signal delivered since the last drain."""
        drained = tuple(self._queue)
        self._queue.clear()
        self._arrived.clear()
        self._control_arrived.clear()
        return drained

    async def wait(self) -> None:
        """Wait until any signal arrives after the last drain."""
        await self._arrived.wait()

    async def wait_control(self) -> None:
        """Wait until a control-lane signal arrives after the last drain."""
        await self._control_arrived.wait()

    def close(self) -> None:
        """Stop accepting signals and detach from the owning publisher."""
        self._closed = True
        self._queue.clear()
        if self._owner is not None:
            self._owner.unsubscribe(self)

    def _on_own_loop(self) -> bool:
        try:
            return get_running_loop() is self._loop
        except RuntimeError:
            # No loop runs in the producer thread; delivery must cross threads.
            return False

    def _accept(self, signal: AgentSignal) -> None:
        # Runs on the run loop, serialized with close(): a signal for another
        # state or for a finished run is rejected in this same critical section.
        if self._closed or signal.agent_state_id != self._state_id:
            return
        self._queue.append(signal)
        self._arrived.set()
        if signal.lane is AgentSignalLane.CONTROL:
            self._control_arrived.set()


@Pod()
class InProcessAgentSignalMailbox(IAgentSignalPublisher, IAgentSignalSubscriber):
    """Default in-process signal hub routing committed signals to run mailboxes."""

    _lock: Lock
    _subscribers: dict[str, list[AgentRunMailbox]]

    def __init__(self) -> None:
        """Create an empty subscriber registry."""
        self._lock = Lock()
        self._subscribers = {}

    @override
    def publish(self, signal: AgentSignal) -> None:
        with self._lock:
            mailboxes = tuple(self._subscribers.get(signal.agent_state_id, ()))
        for mailbox in mailboxes:
            mailbox.deliver(signal)

    @override
    def subscribe(self, state_id: str) -> AgentRunMailbox:
        mailbox = AgentRunMailbox(state_id, get_running_loop(), owner=self)
        with self._lock:
            self._subscribers.setdefault(state_id, []).append(mailbox)
        return mailbox

    def unsubscribe(self, mailbox: AgentRunMailbox) -> None:
        """Detach a closed run mailbox from future publications."""
        with self._lock:
            mailboxes = self._subscribers.get(mailbox.state_id)
            if mailboxes is None or mailbox not in mailboxes:
                return
            mailboxes.remove(mailbox)
            if not mailboxes:
                del self._subscribers[mailbox.state_id]

    def subscriber_count(self, state_id: str) -> int:
        """Return how many live runs currently listen for ``state_id``."""
        with self._lock:
            return len(self._subscribers.get(state_id, ()))
