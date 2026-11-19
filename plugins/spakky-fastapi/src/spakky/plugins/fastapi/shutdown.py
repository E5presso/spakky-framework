"""Server shutdown signal that ends open Server-Sent Events streams.

On SIGTERM uvicorn stops accepting connections and then waits for every open
response to finish before it runs the ASGI lifespan shutdown. A stream that
never ends by itself therefore holds the process until
``timeout_graceful_shutdown`` cancels it, and the lifespan shutdown is too late
to tell the stream to stop. `ShutdownSignalRelay` chains the server's own
SIGTERM/SIGINT handlers while the application serves, so the signal fires as
soon as the server starts shutting down, and every @sse stream registered by
the plugin ends normally once it fires.
"""

from asyncio import (
    AbstractEventLoop,
    CancelledError,
    Future,
    current_task,
    get_running_loop,
)
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator
from logging import getLogger
from signal import Signals, getsignal, signal
from threading import current_thread, main_thread
from types import FrameType

from anyio import CancelScope
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.fastapi.error import AbstractSpakkyFastAPIError

logger = getLogger(__name__)

SHUTDOWN_SIGNALS = (Signals.SIGTERM, Signals.SIGINT)
"""Signals the server handles as a request to shut down gracefully."""

type SignalHandler = Callable[[int, FrameType | None], object]
"""A Python-level signal handler as `signal.signal` installs it."""


class ShutdownGuardOutsideTaskError(AbstractSpakkyFastAPIError):
    """Raised when a stream guard is iterated outside an asyncio task."""

    message = "A shutdown-guarded stream must be iterated inside an asyncio task."


@Pod()
class ServerShutdownSignal:
    """Fires once when the server starts shutting down.

    The plugin fires it from the server's SIGTERM/SIGINT handling and again
    from the lifespan shutdown, and re-arms it when the lifespan starts. A
    controller can inject it to stop its own long-running work, and every
    @sse stream ends normally once it fires, so the client reconnects with
    the SSE retry to another server.
    """

    __triggered: bool
    __waiters: dict[Future[None], AbstractEventLoop]

    def __init__(self) -> None:
        self.__triggered = False
        self.__waiters = {}

    @property
    def triggered(self) -> bool:
        """Whether the server has started shutting down."""
        return self.__triggered

    def trigger(self) -> None:
        """Mark the server as shutting down and wake every waiter.

        Safe to call from any thread: each waiter is released on its own
        event loop.
        """
        self.__triggered = True
        for waiter, loop in tuple(self.__waiters.items()):
            loop.call_soon_threadsafe(self.__release, waiter)

    def reset(self) -> None:
        """Re-arm the signal when the server starts serving again."""
        self.__triggered = False

    async def wait(self) -> None:
        """Return once the server has started shutting down."""
        loop = get_running_loop()
        waiter: Future[None] = loop.create_future()
        # Registered before the flag is read, so a trigger from another
        # thread between the two steps still releases this waiter.
        self.__waiters[waiter] = loop
        try:
            if self.__triggered:
                return
            await waiter
        finally:
            del self.__waiters[waiter]

    async def stream_until_shutdown[T](
        self,
        stream: AsyncIterator[T],
    ) -> AsyncGenerator[T]:
        """Yield the stream's items until it ends or the server shuts down.

        The stream is driven in the consuming task itself, so task-bound
        constructs that span a ``yield`` in the stream (anyio cancel scopes and
        task groups, ``asyncio.timeout``, ``current_task()``-scoped sessions,
        context variable tokens) behave as they do without this guard. When
        the signal fires while the task waits for the next item, that wait is
        cancelled with an asyncio cancellation, which an anyio shield does not
        stop: a shielded await or an ``anyio.to_thread.run_sync`` wait inside
        the stream is interrupted too, while the worker thread keeps running.
        An item the stream still produces is dropped. The stream is then
        closed, so a started generator's ``finally`` runs, and this generator
        returns normally. A cancellation requested by anyone else at the same
        time is propagated, not swallowed.

        Args:
            stream: The event stream an @sse method produced.

        Yields:
            The stream's items, in order.

        Raises:
            ShutdownGuardOutsideTaskError: Iterated outside an asyncio task.
        """
        loop = get_running_loop()
        task = current_task()
        if task is None:
            raise ShutdownGuardOutsideTaskError
        waiter: Future[None] = loop.create_future()
        awaiting_item = False
        interrupted = False

        def interrupt(_: Future[None]) -> None:
            # Runs on the task's loop while the task is suspended, so it is
            # suspended inside the stream exactly when awaiting_item is set.
            nonlocal interrupted
            if awaiting_item and not interrupted:
                interrupted = True
                task.cancel()

        waiter.add_done_callback(interrupt)
        self.__waiters[waiter] = loop
        try:
            while not self.__triggered:
                cancellations_before = task.cancelling()
                awaiting_item = True
                try:
                    item = await anext(stream)
                except StopAsyncIteration:
                    return
                except CancelledError:
                    # Swallow only this guard's own cancellation; one more
                    # pending request came from someone else.
                    if interrupted and task.cancelling() - 1 <= cancellations_before:
                        return
                    raise
                finally:
                    awaiting_item = False
                    if interrupted:
                        # Withdraw the cancellation this guard requested.
                        task.uncancel()
                if interrupted:
                    return
                yield item
        finally:
            del self.__waiters[waiter]
            waiter.remove_done_callback(interrupt)
            waiter.cancel()
            if isinstance(stream, AsyncGenerator):
                # Shielded: an anyio cancel scope keeps cancelling every await
                # of a cancelled task, and the stream must still be closed.
                with CancelScope(shield=True):
                    await stream.aclose()

    def iterate_until_shutdown[T](self, iterator: Iterator[T]) -> Generator[T]:
        """Yield the iterator's items until it ends or the server shuts down.

        A sync @sse generator runs in a worker thread that cannot be
        interrupted, so the signal is checked whenever the generator produces
        an item or asks for the next one. The iterator is then closed, so a
        generator's ``finally`` runs.

        Args:
            iterator: The event iterator a sync @sse method produced.

        Yields:
            The iterator's items, in order.
        """
        try:
            while not self.__triggered:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                if self.__triggered:
                    return
                yield item
        finally:
            if isinstance(iterator, Generator):
                iterator.close()

    def __release(self, waiter: Future[None]) -> None:
        if not waiter.done():
            waiter.set_result(None)


class ShutdownSignalRelay:
    """Chains the server's shutdown signal handlers to a `ServerShutdownSignal`.

    ASGI has no event for the start of a server shutdown, so the relay wraps
    the Python-level SIGTERM/SIGINT handlers the server installed (uvicorn
    installs them before it starts the lifespan). Each signal first fires the
    shutdown signal on the server's event loop and then runs the server's
    handler unchanged. Signals the server left at the default or ignored
    disposition are not touched.
    """

    __shutdown: ServerShutdownSignal
    __loop: AbstractEventLoop
    __previous: dict[Signals, SignalHandler]

    def __init__(
        self,
        shutdown: ServerShutdownSignal,
        loop: AbstractEventLoop,
    ) -> None:
        self.__shutdown = shutdown
        self.__loop = loop
        self.__previous = {}

    def install(self) -> None:
        """Chain the server's handlers; only the main thread can do this."""
        if current_thread() is not main_thread():
            logger.debug(
                "Shutdown signals are not relayed outside the main thread; "
                "SSE streams end at the lifespan shutdown"
            )
            return
        for signal_number in SHUTDOWN_SIGNALS:
            previous = getsignal(signal_number)
            if not callable(previous):
                logger.debug(
                    "No Python handler for %s; it is not relayed",
                    signal_number.name,
                )
                continue
            self.__previous[signal_number] = previous
            signal(signal_number, self.relay)

    def uninstall(self) -> None:
        """Restore each handler this relay replaced and still owns."""
        for signal_number, previous in self.__previous.items():
            if getsignal(signal_number) == self.relay:
                signal(signal_number, previous)
        self.__previous.clear()

    def relay(self, signal_number: int, frame: FrameType | None) -> None:
        """Fire the shutdown signal, then run the server's own handler.

        Args:
            signal_number: The received signal.
            frame: The interrupted stack frame.
        """
        try:
            self.__loop.call_soon_threadsafe(self.__shutdown.trigger)
        finally:
            # The server must still shut down if its loop is already closed.
            self.__previous[Signals(signal_number)](signal_number, frame)
