"""Run-scoped channel for application-defined custom agent events.

Application code running inside an agent run (a tool, or a service a tool
calls) has no handle on the event stream the client receives. This module gives
it one without threading a parameter through every call: an adapter wraps the
runner's neutral stream with ``AgentCustomEvents.merge``, which binds a channel
in a ``ContextVar`` for the task that iterates the source, and
``AgentCustomEvents.emit`` puts a named ``CustomEvent`` on that channel.

The merged stream hands every item to its consumer through one queue, so a
custom event emitted while the source is still awaiting (for example during a
long tool call) reaches the consumer before the source's next event.

The source is iterated by a single pump task for its whole lifetime. The runner
holds task-affine constructs (``asyncio.timeout_at`` and friends) across its
``yield`` points, so advancing it from a fresh task per step would break them.
The pump advances the source only after the consumer has asked for the item
after the previous one, which keeps the source exactly as lazy as iterating it
directly: a slow or disconnected consumer does not let the run race ahead.
"""

from asyncio import AbstractEventLoop, Queue, Task, create_task, get_running_loop, wait
from collections.abc import AsyncGenerator, AsyncIterator
from contextvars import ContextVar, copy_context

from spakky.agent.error import AgentCustomEventChannelUnavailableError
from spakky.agent.event import AgentEvent, AgentEventAttribution, CustomEvent
from spakky.agent.types import JsonObject, JsonValue


class _AgentCustomEventChannel:
    """Queue shared by one merged stream's source pump and custom emitters."""

    def __init__(self, attribution: AgentEventAttribution) -> None:
        self.attribution = attribution
        self._loop: AbstractEventLoop = get_running_loop()
        # ``None`` marks the end of the source; nothing is queued after it.
        self._queue: Queue[AgentEvent | None] = Queue()
        self._open = True

    @property
    def open(self) -> bool:
        """Whether a consumer is still draining this channel."""
        return self._open

    def close(self) -> None:
        """Stop accepting custom events; later emits fail instead of vanishing."""
        self._open = False

    def put(self, event: CustomEvent) -> None:
        """Queue a custom event from the run's loop or from a worker thread."""
        if self._on_channel_loop():
            self._queue.put_nowait(event)
            return
        # ``asyncio.to_thread`` copies the context, so a worker thread sees this
        # channel; an asyncio queue is not thread-safe, so hop to the loop.
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def next(self) -> AgentEvent | None:
        """Return the next merged item, or ``None`` once the source has ended."""
        return await self._queue.get()

    def delivered(self) -> None:
        """Record that the consumer asked for the item after the last one."""
        self._queue.task_done()

    async def pump(self, events: AsyncIterator[AgentEvent]) -> None:
        """Iterate the whole source in this one task, one item per consumer pull."""
        try:
            async for event in events:
                if not self._open:
                    # The consumer is gone. A source that survived the pump's
                    # cancellation (a tool swallowed it, or failed during its
                    # cleanup) must not wait on a queue nobody drains.
                    break
                self._queue.put_nowait(event)
                # Backpressure: resume the source only once the consumer has
                # taken everything queued so far and asked for more.
                await self._queue.join()
        finally:
            try:
                # A cancelled pump leaves a generator source suspended at its
                # ``yield``; closing it here runs the source's cleanup now
                # instead of whenever the garbage collector finalizes it.
                if isinstance(events, AsyncGenerator):
                    await events.aclose()
            finally:
                self._open = False
                self._queue.put_nowait(None)

    def _on_channel_loop(self) -> bool:
        try:
            return get_running_loop() is self._loop
        except RuntimeError:
            # No running loop in this thread: the caller is a worker thread.
            return False


_CHANNEL: ContextVar[_AgentCustomEventChannel | None] = ContextVar(
    "spakky_agent_custom_event_channel",
    default=None,
)
"""Channel of the innermost merged stream whose source runs in this context."""


class AgentCustomEvents:
    """Emit application-defined events into the stream of the current run."""

    @staticmethod
    def listening() -> bool:
        """Return whether ``emit`` would reach a consumer from this context.

        Code that also runs outside a merged stream (a plain ``runner.run()``,
        a background job) checks this before emitting.
        """
        channel = _CHANNEL.get()
        return channel is not None and channel.open

    @staticmethod
    def emit(
        name: str,
        value: JsonValue,
        *,
        metadata: JsonObject | None = None,
    ) -> None:
        """Put a named custom event on the stream of the current run.

        The event keeps its position relative to other events emitted by the
        same producer and is delivered without waiting for the runner's next
        event.

        Args:
            name: Application-defined event name; namespace it (for example
                ``"myapp.turn_part"``) to stay clear of adapter-reserved names.
            value: JSON-compatible payload relayed to the client unchanged.
            metadata: Neutral event metadata for in-process consumers. ``None``
                means unspecified and is stored as an empty object.

        Raises:
            AgentCustomEventChannelUnavailableError: No merged stream is
                listening in this context.
            AgentDefinitionError: ``name`` is blank.
        """
        channel = _CHANNEL.get()
        if channel is None or not channel.open:
            raise AgentCustomEventChannelUnavailableError
        channel.put(
            CustomEvent(
                attribution=channel.attribution,
                name=name,
                value=value,
                metadata=metadata if metadata is not None else {},
            )
        )

    @staticmethod
    async def merge(
        events: AsyncIterator[AgentEvent],
        attribution: AgentEventAttribution,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Yield ``events`` interleaved live with custom events emitted meanwhile.

        Args:
            events: The neutral source stream, typically ``runner.run_events()``.
            attribution: Attribution stamped on every emitted custom event.

        Yields:
            Source events in source order and custom events in emit order.
            Custom events still queued when the source ends are yielded before
            the merged stream ends.

        Raises:
            Exception: Whatever the source raises, after every item queued
                before the failure has been yielded.
        """
        channel = _AgentCustomEventChannel(attribution)
        # A task copies its context when it is created, so the channel is bound
        # in the copy the pump runs in. The caller's context is left untouched:
        # an enclosing merge keeps its own channel, and there is no token to
        # reset from whichever context happens to close this generator.
        context = copy_context()
        context.run(_CHANNEL.set, channel)
        pump = create_task(channel.pump(events), context=context)
        source_finished = False
        try:
            while True:
                item = await channel.next()
                if item is None:
                    source_finished = True
                    break
                yield item
                channel.delivered()
            # The pump queues the end marker as its last action, so it is done;
            # awaiting it re-raises the source's failure or cancellation.
            await pump
        finally:
            channel.close()
            if not source_finished:
                # The consumer stopped early (closed or cancelled): stop the
                # source too and wait for its cleanup before returning.
                pump.cancel()
                await wait((pump,))
                AgentCustomEvents._raise_source_cleanup_failure(pump)

    @staticmethod
    def _raise_source_cleanup_failure(pump: Task[None]) -> None:
        """Surface a source failure an early-stopped consumer would otherwise lose."""
        if pump.cancelled():
            return
        error = pump.exception()
        if error is not None:
            raise error
