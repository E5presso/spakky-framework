"""Runner tests for the live per-run mailbox with control and steering lanes."""

from asyncio import CancelledError, Event, create_task, sleep, wait_for
from collections.abc import AsyncIterator
from dataclasses import replace
from threading import Thread
from typing import override

import pytest

from spakky.agent import (
    Agent,
    AgentEvent,
    AgentRunner,
    AgentSignal,
    AgentSignalInboxConflictError,
    AgentSignalKind,
    AgentSignalPriority,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Error,
    MessageDeltaEvent,
    ModelMessage,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    RunAgentInput,
    RunFinishedEvent,
    InProcessAgentSignalMailbox,
    Token,
    Tool,
)
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingModel,
)
from tests.unit.test_runner import (
    DurableGuardedFrameworkProbeAgent,
    ProbeAgent,
    StatelessProbeAgent,
    _tool_event,
)

YIELD_TO_LOOP_ROUNDS = 5
"""Loop turns granted to a delivered signal; scheduling only, never wall time."""


class _GatedModel(RecordingModel):
    """Streams a draft, then blocks each gated request until its gate opens."""

    def __init__(self, gated_requests: int = 1) -> None:
        super().__init__(())
        self.entered = [Event() for _ in range(gated_requests)]
        self.gates = [Event() for _ in range(gated_requests)]
        self.cancelled = 0
        self.completed_gated = 0

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        index = len(self.requests) - 1
        if index < len(self.gates):
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="draft"
            )
            self.entered[index].set()
            try:
                await self.gates[index].wait()
            except CancelledError:
                self.cancelled += 1
                raise
            self.completed_gated += 1
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="answer"
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


def _steer(
    signal_id: str,
    content: str,
    *,
    input_id: str = "session:utterance",
    revision: int = 1,
    priority: AgentSignalPriority = AgentSignalPriority.NORMAL,
) -> AgentSignal:
    return AgentSignal(
        id=signal_id,
        agent_state_id="run-1",
        kind=AgentSignalKind.STEERING_INSTRUCTION,
        payload={
            "input_id": input_id,
            "revision": revision,
            "content": content,
            "final": True,
        },
        priority=priority,
    )


def _runner(
    model: RecordingModel,
    states: FakeStateRepository,
    signals: FakeSignalRepository,
    evidence: FakeEvidenceRepository,
) -> AgentRunner:
    return AgentRunner.for_agent_instance(ProbeAgent(model, states, signals, evidence))


async def _drive(
    runner: AgentRunner, run_input: RunAgentInput, events_surface: bool
) -> tuple[AgentYield[object] | AgentEvent, ...]:
    if events_surface:
        return tuple([event async for event in runner.run_events(run_input)])
    return tuple([item async for item in runner.run(run_input)])


async def _yield_to_loop() -> None:
    for _ in range(YIELD_TO_LOOP_ROUNDS):
        await sleep(0)


def _steering_contents(request: ModelRequest) -> list[str]:
    return [
        message.content
        for message in request.messages
        if isinstance(message, ModelMessage)
        and message.metadata.get("steering_input_id")
        and isinstance(message.content, str)
    ]


def _repositories() -> tuple[
    FakeStateRepository, FakeSignalRepository, FakeEvidenceRepository
]:
    return FakeStateRepository(), FakeSignalRepository(()), FakeEvidenceRepository()


@pytest.mark.parametrize("events_surface", [False, True])
async def test_runner_mailbox_run_without_new_signals_expect_single_ledger_replay(
    events_surface: bool,
) -> None:
    """A busy or idle run reads the signal ledger once at start and never again."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            events_surface,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    reads_at_start = signals.list_pending_calls
    await _yield_to_loop()

    assert reads_at_start == 1
    assert signals.list_pending_calls == reads_at_start
    model.gates[0].set()
    await wait_for(task, 1)
    assert signals.list_pending_calls == 1
    assert states.get("run-1").status is AgentStatus.COMPLETED


@pytest.mark.parametrize("events_surface", [False, True])
async def test_runner_mailbox_normal_steering_expect_injected_only_at_safe_point(
    events_surface: bool,
) -> None:
    """Ordinary steering never cancels the in-flight response; it lands after it."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            events_surface,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    signals.append(_steer("steer-1", "add detail"))
    await _yield_to_loop()

    assert model.cancelled == 0
    assert len(model.requests) == 1
    model.gates[0].set()
    await wait_for(task, 1)
    assert model.completed_gated == 1
    assert len(model.requests) == 2
    assert _steering_contents(model.requests[1]) == ["add detail"]
    assert signals.list_pending("run-1") == ()


async def test_runner_mailbox_urgent_steering_from_other_thread_expect_immediate_restart() -> (
    None
):
    """A control-lane signal committed on another thread wakes and interrupts the run."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            False,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    producer = Thread(
        target=signals.append,
        args=(
            _steer("urgent", "stop and do this", priority=AgentSignalPriority.URGENT),
        ),
    )
    producer.start()
    producer.join()
    await wait_for(task, 1)

    assert model.cancelled == 1
    assert model.completed_gated == 0
    assert _steering_contents(model.requests[1]) == ["stop and do this"]
    assert states.get("run-1").status is AgentStatus.COMPLETED


@pytest.mark.parametrize("events_surface", [False, True])
async def test_runner_mailbox_cancel_expect_immediate_and_queued_steering_preserved(
    events_surface: bool,
) -> None:
    """Cancel interrupts at once while queued steering stays unconsumed for resume."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            events_surface,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    signals.append(_steer("queued", "later idea"))
    signals.append(
        AgentSignal(id="stop", agent_state_id="run-1", kind=AgentSignalKind.CANCEL)
    )
    await wait_for(task, 1)

    assert model.cancelled == 1
    assert states.get("run-1").status is AgentStatus.CANCELLED
    assert [signal.id for signal in signals.list_pending("run-1")] == ["queued"]


async def test_runner_mailbox_urgent_interrupt_expect_queued_steering_reinjected() -> (
    None
):
    """Interrupting for urgent input re-injects earlier queued steering, never drops it."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            False,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    signals.append(_steer("queued", "first note", input_id="a"))
    signals.append(
        _steer(
            "urgent",
            "urgent note",
            input_id="b",
            priority=AgentSignalPriority.URGENT,
        )
    )
    await wait_for(task, 1)

    assert model.cancelled == 1
    assert _steering_contents(model.requests[1]) == ["first note", "urgent note"]
    assert signals.list_pending("run-1") == ()


async def test_runner_mailbox_stale_revision_and_redelivery_expect_rejected() -> None:
    """An older revision or a re-delivered consumed signal cannot interrupt again."""
    states, signals, evidence = _repositories()
    model = _GatedModel(gated_requests=2)
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            False,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    current = _steer(
        "rev-2", "current", revision=2, priority=AgentSignalPriority.URGENT
    )
    signals.append(current)
    await wait_for(model.entered[1].wait(), 1)
    signals.append(
        _steer("rev-1", "stale", revision=1, priority=AgentSignalPriority.URGENT)
    )
    signals.mailbox.publish(current)
    await _yield_to_loop()

    assert model.cancelled == 1
    assert len(model.requests) == 2
    model.gates[1].set()
    await wait_for(task, 1)
    assert len(model.requests) == 2
    assert _steering_contents(model.requests[1]) == ["current"]
    assert signals.list_pending("run-1") == ()


async def test_runner_mailbox_duplicate_live_delivery_expect_single_revision() -> None:
    """A signal published twice before consumption is admitted once."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    task = create_task(
        _drive(
            _runner(model, states, signals, evidence),
            RunAgentInput(state_id="run-1", instruction="original"),
            False,
        )
    )
    await wait_for(model.entered[0].wait(), 1)
    steer = _steer("steer-1", "note")
    signals.append(steer)
    signals.mailbox.publish(steer)
    model.gates[0].set()
    await wait_for(task, 1)

    assert len(model.requests) == 2
    assert _steering_contents(model.requests[1]) == ["note"]


async def test_runner_without_mailbox_input_wait_expect_typed_configuration_failure() -> (
    None
):
    """A run that must wait for live input fails closed when no mailbox is wired."""
    states, signals, evidence = _repositories()
    runner = replace(
        _runner(_GatedModel(gated_requests=0), states, signals, evidence),
        signal_mailbox=None,
    )

    items = await _drive(
        runner,
        RunAgentInput(
            state_id="run-1", instruction="placeholder", steering_input_required=True
        ),
        False,
    )

    error = items[-1]
    assert isinstance(error, AgentYield) and isinstance(error.payload, Error)
    assert states.get("run-1").status is AgentStatus.FAILED


async def test_runner_mailbox_same_state_twice_expect_inbox_conflict() -> None:
    """One runner cannot open two live inboxes for the same agent state."""
    states, signals, evidence = _repositories()
    model = _GatedModel()
    runner = _runner(model, states, signals, evidence)
    first = create_task(
        _drive(runner, RunAgentInput(state_id="run-1", instruction="a"), False)
    )
    await wait_for(model.entered[0].wait(), 1)

    with pytest.raises(AgentSignalInboxConflictError):
        await _drive(runner, RunAgentInput(state_id="run-1", instruction="b"), False)
    model.gates[0].set()
    await wait_for(first, 1)


@pytest.mark.parametrize("events_surface", [False, True])
async def test_runner_mailbox_guarded_complete_cancel_between_events_expect_cancelled(
    events_surface: bool,
) -> None:
    """Cancel committed while guarded complete() output is replayed stops the step."""
    states, signals, evidence = _repositories()
    runner = AgentRunner.for_agent_instance(
        DurableGuardedFrameworkProbeAgent(RecordingModel(()), states, signals, evidence)
    )
    run_input = RunAgentInput(state_id="run-1", instruction="answer")
    stream = runner.run_events(run_input) if events_surface else runner.run(run_input)
    observed: list[object] = []
    async for item in stream:
        observed.append(item)
        if isinstance(item, MessageDeltaEvent) or (
            isinstance(item, AgentYield) and isinstance(item.payload, Token)
        ):
            signals.append(
                AgentSignal(
                    id="stop", agent_state_id="run-1", kind=AgentSignalKind.CANCEL
                )
            )

    assert states.get("run-1").status is AgentStatus.CANCELLED
    terminal = observed[-1]
    if events_surface:
        assert isinstance(terminal, RunFinishedEvent) and terminal.error is not None
    else:
        assert isinstance(terminal, AgentYield)
        assert terminal.kind is AgentYieldKind.CANCEL


async def test_runner_cancel_at_tool_boundary_expect_queued_steering_unconsumed() -> (
    None
):
    """A cancel pending at the next tool boundary never consumes queued steering first."""
    states, signals, evidence = _repositories()
    model = RecordingModel(
        (
            _tool_event("echo.read", {"value": "one"}, "call-1"),
            _tool_event("echo.read", {"value": "two"}, "call-2"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    runner = _runner(model, states, signals, evidence)

    async for item in runner.run(RunAgentInput(state_id="run-1", instruction="go")):
        if isinstance(item.payload, Tool) and not signals.list_pending("run-1"):
            signals.append(_steer("queued", "later idea"))
            signals.append(
                AgentSignal(
                    id="stop", agent_state_id="run-1", kind=AgentSignalKind.CANCEL
                )
            )

    assert states.get("run-1").status is AgentStatus.CANCELLED
    assert [signal.id for signal in signals.list_pending("run-1")] == ["queued"]


def test_runner_for_agent_instance_expect_bootstrap_bound_mailbox_fallback() -> None:
    """An agent without an injected subscriber uses the mailbox bound at bootstrap."""
    mailbox = InProcessAgentSignalMailbox()
    metadata = Agent.get(StatelessProbeAgent)
    previous = metadata.signal_mailbox
    metadata.signal_mailbox = mailbox
    try:
        runner = AgentRunner.for_agent_instance(StatelessProbeAgent(RecordingModel(())))
    finally:
        metadata.signal_mailbox = previous

    assert runner.signal_mailbox is mailbox
