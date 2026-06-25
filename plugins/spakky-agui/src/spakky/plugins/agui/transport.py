"""Drive an agent run and stream it as AG-UI server-sent events.

``AgUiRunDriver`` is the pipe that connects the runner to the wire: it pulls the
framework runner's native neutral ``AgentEvent`` stream off ``run_events`` —
the lossless taxonomy AG-UI projects one-to-one (ADR-0013 §3) — runs each event
through the projector (``AgentEvent`` -> AG-UI ``BaseEvent``), and encodes each
AG-UI event into an SSE ``data:`` frame.

``run_events`` emits no approval event: when a tool pauses for human approval it
dispatches nothing and the pause lives only in the durable WAIT_FOR_APPROVAL
state. So before the run's terminal ``RUN_FINISHED``, the driver reads that
durable state and, when an approval is pending, injects the deferred-tool request
frame (the AG-UI HITL idiom) ahead of the terminal. After the stream ends it
flushes the projector's open-frame closures so a stream the runner left
mid-message is still well-formed on the wire.
"""

from collections.abc import AsyncIterator

from ag_ui.core import BaseEvent
from ag_ui.encoder import EventEncoder

from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    RunFinishedEvent,
)
from spakky.agent.inbound import RunAgentInput
from spakky.agent.runner import AgentRunner

from spakky.plugins.agui.hitl import project_pending_approval
from spakky.plugins.agui.projector import AgUiProjector


class AgUiRunDriver:
    """Streams one agent run as encoded AG-UI SSE frames."""

    def __init__(
        self,
        runner: AgentRunner,
        run_input: RunAgentInput,
        agent_id: str,
        projector: AgUiProjector,
        encoder: EventEncoder,
    ) -> None:
        self._runner = runner
        self._run_input = run_input
        self._attribution = AgentEventAttribution(
            agent_id=agent_id,
            run_id=run_input.state_id,
            conversation_id=run_input.effective_conversation_id,
        )
        self._projector = projector
        self._encoder = encoder

    async def __aiter__(self) -> AsyncIterator[str]:
        """Yield SSE frames for the full run, including the flush tail."""
        # Phase 1: project every neutral runner event, surfacing a pending
        # approval as a deferred-tool frame just before the terminal RUN_FINISHED.
        async for event in self._runner.run_events(self._run_input):
            for frame in self._frames_for(event):
                yield frame
        # Phase 2: flush any projector frame left open by a truncated stream.
        for frame in self._encode(self._projector.finish()):
            yield frame

    def _frames_for(self, event: AgentEvent) -> list[str]:
        if isinstance(event, RunFinishedEvent):
            return self._encode(
                [
                    *self._project_pending_approval(),
                    *self._projector.project(event),
                ]
            )
        return self._encode(self._projector.project(event))

    def _project_pending_approval(self) -> list[BaseEvent]:
        """Project the durable pending approval, if any, before the terminal.

        A stateless run has no state repository and never pauses, so there is
        nothing to read; a durable run reads its run state and emits the
        deferred-tool request only when it is paused for approval.
        """
        if self._runner.states is None:
            return []
        state = self._runner.states.get_or_none(self._run_input.state_id)
        if state is None:
            return []
        projected: list[BaseEvent] = []
        for approval_event in project_pending_approval(state, self._attribution):
            projected.extend(self._projector.project(approval_event))
        return projected

    def _encode(self, events: list[BaseEvent]) -> list[str]:
        return [self._encoder.encode(event) for event in events]
