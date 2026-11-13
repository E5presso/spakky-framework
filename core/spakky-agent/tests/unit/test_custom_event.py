"""Tests for the run-scoped custom event channel and its merged stream."""

from asyncio import CancelledError, Event, create_task, sleep, to_thread
from collections.abc import AsyncGenerator, AsyncIterator
from contextvars import Context, copy_context

import pytest
from spakky.agent import (
    AgentCustomEventChannelUnavailableError,
    AgentCustomEvents,
    AgentDefinitionError,
    CustomEvent,
)
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    AgentEventKind,
    RunFinishedEvent,
    RunStartedEvent,
)

_ATTRIBUTION = AgentEventAttribution(
    agent_id="assistant", run_id="run-1", conversation_id="conv-1"
)
_INNER_ATTRIBUTION = AgentEventAttribution(
    agent_id="researcher",
    run_id="run-2",
    conversation_id="conv-1",
    parent_run_id="run-1",
)
_STARTED = RunStartedEvent(_ATTRIBUTION)
_FINISHED = RunFinishedEvent(_ATTRIBUTION)

# Loop turns granted to a pump task that must *not* make progress; each turn is
# a bare reschedule, not a timed wait.
_LOOP_TURNS = 5


class _SourceFailure(Exception):
    """Stand-in for an error raised by the neutral source stream."""


class _PlainIteratorSource:
    """A source that is an async iterator but not an async generator."""

    def __init__(self, events: tuple[AgentEvent, ...]) -> None:
        self._events = iter(events)

    def __aiter__(self) -> "_PlainIteratorSource":
        return self

    async def __anext__(self) -> AgentEvent:
        for event in self._events:
            AgentCustomEvents.emit("myapp.step", "before")
            return event
        raise StopAsyncIteration


def _names(events: list[AgentEvent]) -> list[str]:
    return [
        event.name if isinstance(event, CustomEvent) else event.kind.value
        for event in events
    ]


def test_emit_outside_merged_stream_expect_channel_unavailable_error() -> None:
    """병합 스트림 밖에서 emit하면 조용히 버리지 않고 전용 에러를 낸다."""
    assert AgentCustomEvents.listening() is False
    with pytest.raises(AgentCustomEventChannelUnavailableError):
        AgentCustomEvents.emit("myapp.turn_part", {"index": 0})


def test_custom_event_blank_name_expect_definition_error() -> None:
    """공백 이름의 custom event는 framework 에러로 거부된다."""
    with pytest.raises(AgentDefinitionError):
        CustomEvent(_ATTRIBUTION, name="  ", value=None)


async def test_merge_without_emits_expect_source_events_in_order() -> None:
    """emit이 없으면 병합 스트림은 원본 이벤트를 순서대로 그대로 전달한다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        yield _STARTED
        yield _FINISHED

    merged = [event async for event in AgentCustomEvents.merge(source(), _ATTRIBUTION)]

    assert merged == [_STARTED, _FINISHED]
    assert AgentCustomEvents.listening() is False


async def test_merge_emit_during_pending_source_expect_delivered_live() -> None:
    """원본이 아직 대기 중일 때 emit된 이벤트가 원본의 다음 이벤트보다 먼저 도착한다."""
    release = Event()

    async def source() -> AsyncGenerator[AgentEvent, None]:
        yield _STARTED
        AgentCustomEvents.emit(
            "myapp.turn_part", {"index": 0}, metadata={"origin": "tool"}
        )
        # Stands for a long tool call: the source yields nothing until released.
        await release.wait()
        yield _FINISHED

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)

    assert await anext(merged) is _STARTED
    custom = await anext(merged)
    # The custom event arrived although the source is still blocked.
    assert release.is_set() is False
    assert custom == CustomEvent(
        _ATTRIBUTION,
        name="myapp.turn_part",
        value={"index": 0},
        metadata={"origin": "tool"},
    )
    assert custom.kind is AgentEventKind.CUSTOM
    release.set()
    assert await anext(merged) is _FINISHED
    with pytest.raises(StopAsyncIteration):
        await anext(merged)


async def test_merge_emit_blank_name_expect_definition_error_at_emit_site() -> None:
    """공백 이름은 emit 호출 지점에서 거부되어 원본 스트림의 실패로 전파된다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit(" ", 1)
        yield _STARTED

    with pytest.raises(AgentDefinitionError):
        async for _ in AgentCustomEvents.merge(source(), _ATTRIBUTION):
            pass


async def test_merge_expect_listening_only_inside_source() -> None:
    """채널은 원본을 순회하는 context 안에서만 보이고 소비자 context는 건드리지 않는다."""
    observed: list[bool] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        observed.append(AgentCustomEvents.listening())
        yield _STARTED

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    await anext(merged)

    assert observed == [True]
    assert AgentCustomEvents.listening() is False
    await merged.aclose()


async def test_merge_expect_source_advances_only_when_consumer_pulls() -> None:
    """소비자가 다음 항목을 요청하기 전에는 원본이 앞서 진행하지 않는다."""
    progress: list[str] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        yield _STARTED
        progress.append("advanced")
        yield _FINISHED

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    assert await anext(merged) is _STARTED
    for _ in range(_LOOP_TURNS):
        await sleep(0)

    assert progress == []
    assert await anext(merged) is _FINISHED
    assert progress == ["advanced"]
    await merged.aclose()


async def test_merge_custom_emitted_before_source_end_expect_delivered() -> None:
    """원본이 끝날 때 아직 전달되지 않은 custom event도 스트림 종료 전에 전달된다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        yield _STARTED
        AgentCustomEvents.emit("myapp.first", 1)
        AgentCustomEvents.emit("myapp.second", 2)

    merged = [event async for event in AgentCustomEvents.merge(source(), _ATTRIBUTION)]

    assert _names(merged) == ["run_started", "myapp.first", "myapp.second"]


async def test_merge_source_failure_expect_queued_items_then_error() -> None:
    """원본 예외는 이미 큐에 들어간 항목이 전달된 뒤 소비자에게 전파된다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        yield _STARTED
        AgentCustomEvents.emit("myapp.before_failure", 1)
        raise _SourceFailure

    received: list[AgentEvent] = []
    with pytest.raises(_SourceFailure):
        async for event in AgentCustomEvents.merge(source(), _ATTRIBUTION):
            received.append(event)

    assert _names(received) == ["run_started", "myapp.before_failure"]


async def test_merge_closed_at_source_event_expect_source_cleanup_runs() -> None:
    """소비자가 원본 이벤트에서 일찍 닫으면 pump가 취소되고 원본 정리가 실행된다."""
    cleaned: list[str] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        try:
            yield _STARTED
            yield _FINISHED
        finally:
            cleaned.append("source")

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    assert await anext(merged) is _STARTED

    await merged.aclose()

    assert cleaned == ["source"]


async def test_merge_closed_while_source_awaits_expect_source_cancelled() -> None:
    """원본이 대기 중일 때 닫으면 원본의 await 지점에 취소가 전달된다."""
    never = Event()
    outcome: list[str] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit("myapp.progress", 1)
        try:
            await never.wait()
        except CancelledError:
            outcome.append("cancelled")
            raise
        yield _STARTED

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    assert _names([await anext(merged)]) == ["myapp.progress"]

    await merged.aclose()

    assert outcome == ["cancelled"]


async def test_merge_consumer_task_cancelled_expect_source_cancelled() -> None:
    """소비자 task가 취소되면(클라이언트 연결 종료) pump도 취소되어 남지 않는다."""
    started = Event()
    never = Event()
    outcome: list[str] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        started.set()
        try:
            await never.wait()
        finally:
            outcome.append("cleaned")
        yield _STARTED

    async def consume() -> None:
        async for _ in AgentCustomEvents.merge(source(), _ATTRIBUTION):
            pass

    consumer = create_task(consume())
    await started.wait()
    consumer.cancel()

    with pytest.raises(CancelledError):
        await consumer
    assert outcome == ["cleaned"]


async def test_merge_consumer_cancelled_source_survives_expect_no_hang() -> None:
    """취소를 삼키고 계속 yield하는 원본이어도 소비자 취소가 멈추지 않고 정리된다."""
    started = Event()
    never = Event()
    outcome: list[str] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        started.set()
        try:
            await never.wait()
        except CancelledError:
            outcome.append("swallowed")
        try:
            yield _STARTED
            yield _STARTED
        finally:
            outcome.append("cleaned")

    async def consume() -> None:
        async for _ in AgentCustomEvents.merge(source(), _ATTRIBUTION):
            pass

    consumer = create_task(consume())
    await started.wait()
    consumer.cancel()

    with pytest.raises(CancelledError):
        await consumer
    assert outcome == ["swallowed", "cleaned"]


async def test_merge_closed_after_source_finished_expect_clean_close() -> None:
    """원본이 이미 끝난 뒤 남은 custom event에서 닫아도 조용히 정리된다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit("myapp.only", 1)
        return
        yield _STARTED  # pragma: no cover - marks this function as a generator

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    assert _names([await anext(merged)]) == ["myapp.only"]

    await merged.aclose()

    with pytest.raises(StopAsyncIteration):
        await anext(merged)


async def test_merge_closed_after_source_failed_expect_failure_surfaced() -> None:
    """일찍 닫는 소비자도 이미 발생한 원본 실패를 잃지 않는다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit("myapp.only", 1)
        raise _SourceFailure
        yield _STARTED  # pragma: no cover - marks this function as a generator

    merged = AgentCustomEvents.merge(source(), _ATTRIBUTION)
    assert _names([await anext(merged)]) == ["myapp.only"]

    with pytest.raises(_SourceFailure):
        await merged.aclose()


async def test_merge_plain_iterator_source_expect_merged_without_aclose() -> None:
    """async generator가 아닌 iterator 원본도 같은 순서 규칙으로 병합된다."""
    source: AsyncIterator[AgentEvent] = _PlainIteratorSource((_STARTED, _FINISHED))

    merged = [event async for event in AgentCustomEvents.merge(source, _ATTRIBUTION)]

    assert _names(merged) == [
        "myapp.step",
        "run_started",
        "myapp.step",
        "run_finished",
    ]


async def test_merge_emit_from_worker_thread_expect_delivered_in_order() -> None:
    """to_thread로 넘긴 동기 코드의 emit도 같은 채널로 순서대로 전달된다."""

    async def source() -> AsyncGenerator[AgentEvent, None]:
        await to_thread(AgentCustomEvents.emit, "myapp.from_thread", {"ok": True})
        yield _STARTED

    merged = [event async for event in AgentCustomEvents.merge(source(), _ATTRIBUTION)]

    assert _names(merged) == ["myapp.from_thread", "run_started"]


async def test_merge_nested_expect_innermost_channel_then_outer_restored() -> None:
    """중첩 병합은 가장 안쪽 채널에 묶이고 끝나면 바깥 채널이 그대로 남는다."""

    async def inner_source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit("myapp.inner", 2)
        yield RunStartedEvent(_INNER_ATTRIBUTION)

    async def outer_source() -> AsyncGenerator[AgentEvent, None]:
        AgentCustomEvents.emit("myapp.outer_before", 1)
        async for event in AgentCustomEvents.merge(inner_source(), _INNER_ATTRIBUTION):
            yield event
        AgentCustomEvents.emit("myapp.outer_after", 3)

    merged = [
        event async for event in AgentCustomEvents.merge(outer_source(), _ATTRIBUTION)
    ]

    assert _names(merged) == [
        "myapp.outer_before",
        "myapp.inner",
        "run_started",
        "myapp.outer_after",
    ]
    assert [event.attribution.run_id for event in merged] == [
        "run-1",
        "run-2",
        "run-2",
        "run-1",
    ]


async def test_emit_after_merged_stream_ended_expect_channel_unavailable() -> None:
    """실행이 끝난 뒤 남은 context에서 emit하면 버려지지 않고 에러가 난다."""
    captured: list[Context] = []

    async def source() -> AsyncGenerator[AgentEvent, None]:
        captured.append(copy_context())
        yield _STARTED

    async for _ in AgentCustomEvents.merge(source(), _ATTRIBUTION):
        pass
    stale = captured[0]

    assert stale.run(AgentCustomEvents.listening) is False
    with pytest.raises(AgentCustomEventChannelUnavailableError):
        stale.run(AgentCustomEvents.emit, "myapp.late", 1)
