"""Tests for non-blocking agent signal consumption."""

from collections.abc import AsyncGenerator, Sequence

import pytest

from spakky.agent import (
    AgentDefinitionError,
    AgentSignal,
    AgentSignalKind,
    AgentSignalPollPoint,
    AgentYield,
    AgentYieldKind,
    Final,
    IAgentSignalRepository,
    Progress,
    Token,
    consume_pending_agent_signals,
)


class InboundSignalQueue(IAgentSignalRepository):
    """Test double that behaves like an append-ordered inbound adapter queue."""

    def __init__(self) -> None:
        self._pending: list[AgentSignal] = []
        self.consumed_ids: list[str] = []

    def append(self, signal: AgentSignal) -> AgentSignal:
        self._pending.append(signal)
        return signal

    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(
            signal for signal in self._pending if signal.agent_state_id == state_id
        )

    def mark_consumed(self, signal_id: str) -> AgentSignal:
        for index, signal in enumerate(self._pending):
            if signal.id == signal_id:
                self.consumed_ids.append(signal_id)
                return self._pending.pop(index)
        raise AgentDefinitionError("Queued agent signal was not found")


def test_consume_pending_agent_signals_expect_preserves_queue_order() -> None:
    """user message, approval, cancel, resume 신호를 append 순서로 소비한다."""
    queue = InboundSignalQueue()
    for signal in (
        AgentSignal("signal-1", "run-1", AgentSignalKind.USER_MESSAGE),
        AgentSignal("signal-2", "run-1", AgentSignalKind.APPROVAL_DECISION),
        AgentSignal("signal-3", "run-1", AgentSignalKind.CANCEL),
        AgentSignal("signal-4", "run-1", AgentSignalKind.RESUME),
    ):
        queue.append(signal)

    batch = consume_pending_agent_signals(
        queue,
        "run-1",
        poll_point=AgentSignalPollPoint.ACTION_BOUNDARY,
    )

    assert batch.poll_point == AgentSignalPollPoint.ACTION_BOUNDARY
    assert [signal.id for signal in batch.signals] == [
        "signal-1",
        "signal-2",
        "signal-3",
        "signal-4",
    ]
    assert queue.consumed_ids == ["signal-1", "signal-2", "signal-3", "signal-4"]


def test_consume_pending_agent_signals_expect_does_not_overtake_unaccepted_signal() -> (
    None
):
    """later accepted signal이 earlier unaccepted signal을 앞질러 소비되지 않는다."""
    queue = InboundSignalQueue()
    queue.append(AgentSignal("signal-1", "run-1", AgentSignalKind.EXTERNAL_EVENT))
    queue.append(AgentSignal("signal-2", "run-1", AgentSignalKind.USER_MESSAGE))

    batch = consume_pending_agent_signals(
        queue,
        "run-1",
        accepted_signals=(AgentSignalKind.USER_MESSAGE,),
    )

    assert batch.consumed_count == 0
    assert queue.consumed_ids == []
    assert [signal.id for signal in queue.list_pending("run-1")] == [
        "signal-1",
        "signal-2",
    ]


async def test_inbound_adapter_append_expect_running_stream_polls_without_waiting() -> (
    None
):
    """inbound adapter가 실행 중 append한 signal을 stream tick에서 소비한다."""
    queue = InboundSignalQueue()

    async def execute() -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(kind=AgentYieldKind.TOKEN, payload=Token("hel"))
        queue.append(
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "continue"},
            )
        )
        batch = consume_pending_agent_signals(
            queue,
            "run-1",
            poll_point=AgentSignalPollPoint.MODEL_STREAM_TICK,
            accepted_signals=(AgentSignalKind.USER_MESSAGE,),
        )
        for signal in batch.signals:
            yield AgentYield(
                kind=AgentYieldKind.PROGRESS,
                payload=Progress(f"signal:{signal.kind.value}"),
            )
        yield AgentYield(kind=AgentYieldKind.TOKEN, payload=Token("lo"))
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output="done", metadata={}),
        )

    events = [item async for item in execute()]

    assert [event.kind for event in events] == [
        AgentYieldKind.TOKEN,
        AgentYieldKind.PROGRESS,
        AgentYieldKind.TOKEN,
        AgentYieldKind.FINAL,
    ]
    assert queue.consumed_ids == ["signal-1"]


def test_consume_pending_agent_signals_expect_rejects_invalid_poll_arguments() -> None:
    """poll argument 오류가 custom error로 드러난다."""
    queue = InboundSignalQueue()

    with pytest.raises(AgentDefinitionError):
        consume_pending_agent_signals(queue, " ")
    with pytest.raises(AgentDefinitionError):
        consume_pending_agent_signals(queue, "run-1", max_signals=0)
