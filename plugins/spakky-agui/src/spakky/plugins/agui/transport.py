"""Drive an agent run and stream it as AG-UI server-sent events.

``AgUiRunDriver`` is the pipe that connects the runner to the wire: it pulls the
framework runner's native neutral ``AgentEvent`` stream off ``run_events`` —
the lossless taxonomy AG-UI projects one-to-one (ADR-0013 §3) — runs each event
through the projector (``AgentEvent`` -> AG-UI ``BaseEvent``), and encodes each
AG-UI event into an SSE ``data:`` frame.

``run_events`` emits approval pauses as neutral ``RunPausedEvent`` items. The
projector maps those directly into AG-UI's deferred-tool request idiom. After the
stream ends the driver flushes the projector's open-frame closures so a stream
the runner left mid-message is still well-formed on the wire.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager

from ag_ui.core import BaseEvent
from ag_ui.encoder import EventEncoder

from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
)
from spakky.agent.inbound import RunAgentInput
from spakky.agent.runner import AgentRunner

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint_input import AgUiInboundRun
from spakky.plugins.agui.error import AgUiApprovalDecodeError
from spakky.plugins.agui.hitl import ingest_decision
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
        # Phase 1: project every neutral runner event.
        async for event in self._runner.run_events(self._run_input):
            for frame in self._frames_for(event):
                yield frame
        # Phase 2: flush any projector frame left open by a truncated stream.
        for frame in self._encode(self._projector.finish()):
            yield frame

    def _frames_for(self, event: AgentEvent) -> list[str]:
        return self._encode(self._projector.project(event))

    def _encode(self, events: list[BaseEvent]) -> list[str]:
        return [self._encoder.encode(event) for event in events]


class AgUiManagedRunDriver:
    """Open a request-scoped runner for the lifetime of one AG-UI stream."""

    def __init__(
        self,
        runner_context: AbstractAsyncContextManager[AgentRunner],
        inbound: AgUiInboundRun,
        agent_id: str,
        config: AgUiConfig,
        accept: str | None,
    ) -> None:
        self._runner_context = runner_context
        self._inbound = inbound
        self._agent_id = agent_id
        self._config = config
        self._accept = accept

    async def __aiter__(self) -> AsyncIterator[str]:
        """Yield frames while the runner factory context remains open."""
        async with self._runner_context as runner:
            if self._inbound.core_input.resume:
                if runner.signals is None:
                    raise AgUiApprovalDecodeError
                ingest_decision(
                    self._inbound.ag_ui_input,
                    runner.signals,
                    self._inbound.core_input.state_id,
                )
            driver = AgUiRunDriver(
                runner=runner,
                run_input=self._inbound.core_input,
                agent_id=self._agent_id,
                projector=AgUiProjector(self._config),
                encoder=EventEncoder(accept=self._accept or ""),
            )
            async for frame in driver:
                yield frame
