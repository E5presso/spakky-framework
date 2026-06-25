"""Unit tests for the SpakkyAgentExecutor request/cancel branches."""

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskState,
    TaskStatus,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from spakky.agent.execution import (
    Agent,
    AgentExecutionSpec,
    AgentSignalKind,
    RecoveryStrategy,
)
from spakky.agent.interfaces.model import IAgentModel
from spakky.agent.signal import ApprovalDecision
from spakky.agent.state import AgentState, AgentStateReason, AgentStatus
from spakky.agent.types import JsonObject

from spakky.plugins.a2a.error import InvalidApprovalDecisionError
from spakky.plugins.a2a.executor.adapter import (
    SpakkyAgentExecutor,
    _InboundApproval,
)
from spakky.plugins.a2a.executor.event_mapping import AgentEventProjector, RunOutcome
from tests.unit._sample_agents import StubModel
from tests.unit.conftest import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingEventQueue,
)


@Agent(
    spec=AgentExecutionSpec(
        name="durable",
        accepted_signals=(AgentSignalKind.CANCEL,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class _DurableAgent:
    """Durable agent exposing a signal repository for cancel/approval tests."""

    def __init__(
        self,
        model: IAgentModel,
        signals: FakeSignalRepository,
        states: FakeStateRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._signals = signals
        self._states = states
        self._evidence = evidence


@Agent(spec=AgentExecutionSpec(name="stateless"))
class _StatelessAgent:
    """Stateless agent with no durable signal repository injected."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


def _data_part(payload: dict[str, object]) -> Part:
    value = Value()
    ParseDict(payload, value)
    return Part(data=value)


def _context(parts: list[Part]) -> RequestContext:
    request = SendMessageRequest(
        message=Message(role=Role.ROLE_USER, message_id="m1", parts=parts)
    )
    return RequestContext(
        call_context=ServerCallContext(),
        request=request,
        task_id="t1",
        context_id="c1",
    )


def _durable_executor() -> tuple[SpakkyAgentExecutor, FakeSignalRepository]:
    signals = FakeSignalRepository()
    agent = _DurableAgent(
        StubModel(), signals, FakeStateRepository(), FakeEvidenceRepository()
    )
    return SpakkyAgentExecutor(agent, AgentEventProjector()), signals


def test_inbound_approval_absent_without_message() -> None:
    """A request context carrying no message yields no inbound approval."""
    executor, _ = _durable_executor()

    context = RequestContext(
        call_context=ServerCallContext(),
        task_id="t1",
        context_id="c1",
    )

    assert executor._inbound_approval(context) is None


def test_inbound_approval_absent_without_data_part() -> None:
    """A message with only text parts yields no inbound approval."""
    executor, _ = _durable_executor()

    assert executor._inbound_approval(_context([Part(text="hi")])) is None


def test_inbound_approval_absent_without_approval_id() -> None:
    """A data part lacking an approval id yields no inbound approval."""
    executor, _ = _durable_executor()

    context = _context([_data_part({"decision": "approve"})])

    assert executor._inbound_approval(context) is None


def test_inbound_approval_parsed_from_data_part() -> None:
    """A data part with approval id and decision yields a parsed approval."""
    executor, _ = _durable_executor()

    context = _context([_data_part({"approval_id": "a1", "decision": "approve"})])

    approval = executor._inbound_approval(context)
    assert approval is not None
    assert approval.approval_id == "a1"


def test_parse_decision_rejects_non_string() -> None:
    """A non-string decision value is rejected as an invalid decision."""
    executor, _ = _durable_executor()

    context = _context([_data_part({"approval_id": "a1", "decision": 1})])

    with pytest.raises(InvalidApprovalDecisionError):
        executor._inbound_approval(context)


def test_parse_decision_rejects_unknown_value() -> None:
    """An unknown decision string is rejected as an invalid decision."""
    executor, _ = _durable_executor()

    context = _context([_data_part({"approval_id": "a1", "decision": "maybe"})])

    with pytest.raises(InvalidApprovalDecisionError):
        executor._inbound_approval(context)


def test_append_approval_signal_without_repository_raises() -> None:
    """A stateless agent cannot accept an approval decision signal."""
    executor = SpakkyAgentExecutor(_StatelessAgent(StubModel()), AgentEventProjector())
    approval = _InboundApproval(approval_id="a1", decision=ApprovalDecision.APPROVE)

    with pytest.raises(InvalidApprovalDecisionError):
        executor._append_approval_signal("t1", approval)


async def test_cancel_without_repository_publishes_canceled(
    queue: RecordingEventQueue,
) -> None:
    """A stateless agent cancel publishes a canceled status with no signal repo."""
    executor = SpakkyAgentExecutor(_StatelessAgent(StubModel()), AgentEventProjector())

    await executor.cancel(_context([Part(text="x")]), queue)

    states = [status.status.state for status in queue.status_updates()]
    assert TaskState.TASK_STATE_CANCELED in states


async def test_cancel_with_repository_appends_cancel_signal(
    queue: RecordingEventQueue,
) -> None:
    """A durable agent cancel appends a cancel signal and publishes canceled."""
    executor, signals = _durable_executor()

    await executor.cancel(_context([Part(text="x")]), queue)

    appended = signals.appended()
    assert any(signal.kind is AgentSignalKind.CANCEL for signal in appended)
    states = [status.status.state for status in queue.status_updates()]
    assert TaskState.TASK_STATE_CANCELED in states


async def test_ensure_task_enqueues_submitted_task_when_absent(
    queue: RecordingEventQueue,
) -> None:
    """A fresh request enqueues a submitted Task before any status update."""
    task = await SpakkyAgentExecutor._ensure_task(_context([Part(text="x")]), queue)

    assert task.status.state == TaskState.TASK_STATE_SUBMITTED
    assert any(isinstance(event, Task) for event in queue.events)


async def test_ensure_task_reuses_current_task_on_resume(
    queue: RecordingEventQueue,
) -> None:
    """A resume request reuses the existing current task without re-enqueuing."""
    existing = Task(
        id="t1", context_id="c1", status=TaskStatus(state=TaskState.TASK_STATE_WORKING)
    )
    context = _context([Part(text="x")])
    context.current_task = existing

    task = await SpakkyAgentExecutor._ensure_task(context, queue)

    assert task is existing
    assert queue.events == []


def _interrupted_state(metadata: JsonObject) -> AgentState:
    return AgentState(
        id="t1",
        agent_type="durable",
        status=AgentStatus.COMPLETED,
        reason=AgentStateReason.APPROVAL_REQUIRED,
        metadata=metadata,
    )


async def test_reconcile_terminal_completes_a_clean_run(
    queue: RecordingEventQueue,
) -> None:
    """With no pause and a successful outcome the task completes."""
    executor, _ = _durable_executor()
    updater = TaskUpdater(queue, task_id="t1", context_id="c1")

    await executor._reconcile_terminal("t1", RunOutcome(error=None), updater)

    states = [status.status.state for status in queue.status_updates()]
    assert TaskState.TASK_STATE_COMPLETED in states


async def test_reconcile_terminal_fails_on_error_outcome(
    queue: RecordingEventQueue,
) -> None:
    """A RUN_FINISHED error outcome marks the task failed with the error text."""
    executor, _ = _durable_executor()
    updater = TaskUpdater(queue, task_id="t1", context_id="c1")

    await executor._reconcile_terminal(
        "t1", RunOutcome(error={"code": "boom", "message": "exploded"}), updater
    )

    status = queue.status_updates()[0]
    assert status.status.state == TaskState.TASK_STATE_FAILED
    assert MessageToDict(status.status.message.parts[0]) == {"text": "exploded"}


async def test_reconcile_terminal_failure_uses_fallback_message(
    queue: RecordingEventQueue,
) -> None:
    """A failure outcome without a message falls back to a generic failure text."""
    executor, _ = _durable_executor()
    updater = TaskUpdater(queue, task_id="t1", context_id="c1")

    await executor._reconcile_terminal("t1", RunOutcome(error={"code": "x"}), updater)

    status = queue.status_updates()[0]
    assert MessageToDict(status.status.message.parts[0]) == {"text": "run failed"}


async def test_reconcile_terminal_pauses_for_approval(
    queue: RecordingEventQueue,
) -> None:
    """A durable APPROVAL_REQUIRED state pauses the task for input."""
    signals = FakeSignalRepository()
    states = FakeStateRepository()
    states.save(
        _interrupted_state(
            {"approval": {"id": "approval:t1:write", "allowed_decisions": ["approve"]}}
        )
    )
    agent = _DurableAgent(StubModel(), signals, states, FakeEvidenceRepository())
    executor = SpakkyAgentExecutor(agent, AgentEventProjector())
    updater = TaskUpdater(queue, task_id="t1", context_id="c1")

    await executor._reconcile_terminal("t1", RunOutcome(error=None), updater)

    status = queue.status_updates()[0]
    assert status.status.state == TaskState.TASK_STATE_INPUT_REQUIRED
    parts = [MessageToDict(part) for part in status.status.message.parts]
    assert parts[1]["data"]["approval_id"] == "approval:t1:write"


async def test_reconcile_terminal_approval_uses_prompt_fallback(
    queue: RecordingEventQueue,
) -> None:
    """A pending approval without a prompt falls back to a generic pause message."""
    states = FakeStateRepository()
    states.save(_interrupted_state({"approval": {"id": "approval:t1:write"}}))
    agent = _DurableAgent(
        StubModel(), FakeSignalRepository(), states, FakeEvidenceRepository()
    )
    executor = SpakkyAgentExecutor(agent, AgentEventProjector())
    updater = TaskUpdater(queue, task_id="t1", context_id="c1")

    await executor._reconcile_terminal("t1", RunOutcome(error=None), updater)

    status = queue.status_updates()[0]
    assert MessageToDict(status.status.message.parts[0]) == {
        "text": "Approval required to continue."
    }


def test_pending_approval_absent_without_state_repository() -> None:
    """A stateless agent never reports a pending approval pause."""
    executor = SpakkyAgentExecutor(_StatelessAgent(StubModel()), AgentEventProjector())

    assert executor._pending_approval("t1") is None


def test_pending_approval_absent_when_metadata_is_malformed() -> None:
    """An APPROVAL_REQUIRED state with non-mapping approval metadata reports None."""
    states = FakeStateRepository()
    states.save(_interrupted_state({"approval": "not-a-mapping"}))
    agent = _DurableAgent(
        StubModel(), FakeSignalRepository(), states, FakeEvidenceRepository()
    )
    executor = SpakkyAgentExecutor(agent, AgentEventProjector())

    assert executor._pending_approval("t1") is None
