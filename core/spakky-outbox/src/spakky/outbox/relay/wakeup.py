"""Signal that wakes the outbox relays once stored messages are committed."""

import logging
from collections.abc import Callable
from threading import Lock

from spakky.core.pod.annotations.pod import Pod

logger = logging.getLogger(__name__)

type OutboxRelayWaker = Callable[[], None]
"""Makes one running relay read the outbox now instead of at its next poll."""


@Pod()
class OutboxRelayWakeup:
    """Connects the outbox event buses to the running relays.

    A bus that stored a message asks for ``notify()`` after its transaction
    commits; every relay subscribed at that moment then reads the outbox right
    away. Polling stays as the recovery path for whatever this misses.
    Framework-internal: applications do not call it.
    """

    _lock: Lock
    _wakers: tuple[OutboxRelayWaker, ...]

    def __init__(self) -> None:
        self._lock = Lock()
        self._wakers = ()

    def subscribe(self, waker: OutboxRelayWaker) -> None:
        """Start waking ``waker`` on every notification.

        Args:
            waker: Callable that wakes one relay. Must be safe to call from any
                thread.
        """
        with self._lock:
            if waker not in self._wakers:
                self._wakers = (*self._wakers, waker)

    def unsubscribe(self, waker: OutboxRelayWaker) -> None:
        """Stop waking ``waker``.

        Args:
            waker: Callable previously passed to ``subscribe``.
        """
        with self._lock:
            self._wakers = tuple(w for w in self._wakers if w != waker)

    def notify(self) -> None:
        """Wake every subscribed relay.

        A relay that cannot be woken is logged and skipped so the others still
        wake; it sends the messages at its next poll instead.
        """
        with self._lock:
            wakers = self._wakers
        for waker in wakers:
            try:
                waker()
            except Exception:
                logger.exception("Failed to wake outbox relay %r", waker)
