"""Runner tests for calling synchronous persistence ports off the event loop."""

from asyncio import CancelledError, create_task, get_running_loop, to_thread
from datetime import UTC, datetime, timedelta
from threading import Event as ThreadEvent
from threading import get_ident
from typing import override

import pytest

from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentRunner,
    AgentState,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    ModelStreamEvent,
    ModelStreamEventKind,
    RunAgentInput,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.runner import EVIDENCE_CLOCK_STEP, _EvidenceClock
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingModel,
)
from tests.unit.test_runner import ProbeAgent

RELEASE_TIMEOUT_SECONDS = 10.0
"""Safety bound of a blocked fake save; reached only when the loop is stalled."""


class _GatedStateRepository(FakeStateRepository):
    """State store whose first save blocks its thread until released."""

    def __init__(self, *, fail_after_release: bool = False) -> None:
        super().__init__()
        self.entered = ThreadEvent()
        self.release = ThreadEvent()
        self.released_in_time = False
        self.finished = False
        self.save_threads: set[int] = set()
        self._fail_after_release = fail_after_release

    @override
    def save(self, state: AgentState) -> AgentState:
        self.save_threads.add(get_ident())
        if not self.entered.is_set():
            self.entered.set()
            self.released_in_time = self.release.wait(RELEASE_TIMEOUT_SECONDS)
            self.finished = True
            if self._fail_after_release:
                raise AgentDefinitionError("Gated save failed")
        return super().save(state)


def _runner(
    states: FakeStateRepository, evidence: FakeEvidenceRepository
) -> AgentRunner:
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="answer"
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    return AgentRunner.for_agent_instance(
        ProbeAgent(model, states, FakeSignalRepository(()), evidence)
    )


async def _collect(
    runner: AgentRunner, run_input: RunAgentInput
) -> list[AgentYield[object]]:
    return [item async for item in runner.run(run_input)]


async def test_runner_sync_repository_blocked_expect_event_loop_keeps_running() -> None:
    """동기 저장소가 막혀 있어도 같은 루프의 다른 코루틴이 돌아 그 저장소를 풀어 준다."""
    states = _GatedStateRepository()
    runner = _runner(states, FakeEvidenceRepository())
    loop_thread = get_ident()

    run = create_task(
        _collect(runner, RunAgentInput(state_id="run-1", instruction="go"))
    )
    await to_thread(states.entered.wait)
    states.release.set()
    items = await run

    assert states.released_in_time
    assert items[-1].kind is AgentYieldKind.FINAL
    assert loop_thread not in states.save_threads


@pytest.mark.parametrize("fail_after_release", [False, True])
async def test_runner_cancelled_during_sync_repository_call_expect_call_awaited(
    fail_after_release: bool,
) -> None:
    """실행이 취소되어도 진행 중인 동기 저장소 호출이 끝난 뒤에 취소가 전파된다."""
    states = _GatedStateRepository(fail_after_release=fail_after_release)
    runner = _runner(states, FakeEvidenceRepository())
    run = create_task(
        _collect(runner, RunAgentInput(state_id="run-1", instruction="go"))
    )
    await to_thread(states.entered.wait)

    run.cancel()
    get_running_loop().call_soon(states.release.set)
    with pytest.raises(CancelledError):
        await run

    assert states.finished
    assert states.released_in_time


async def test_runner_evidence_expect_strictly_increasing_utc_timestamps() -> None:
    """실행기가 넣는 증거는 넣은 순서대로 증가하는 UTC 시각을 갖는다."""
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()

    await _collect(
        _runner(states, evidence), RunAgentInput(state_id="run-1", instruction="go")
    )

    recorded = evidence.list_by_state("run-1")
    stamps = [item.created_at for item in recorded if item.created_at is not None]
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert AgentEvidenceKind.MODEL in {item.kind for item in recorded}
    assert len(stamps) == len(recorded) > 1
    assert all(stamp.tzinfo is UTC for stamp in stamps)
    assert all(earlier < later for earlier, later in zip(stamps, stamps[1:]))


def test_evidence_clock_stalled_source_expect_strictly_increasing() -> None:
    """시계가 나아가지 않아도 증거 시각은 앞선 값보다 뒤로 간다."""
    frozen = datetime(2026, 11, 27, tzinfo=UTC)
    clock = _EvidenceClock(now=lambda: frozen)

    stamps = [clock.next(), clock.next(), clock.next()]

    assert stamps == [
        frozen,
        frozen + EVIDENCE_CLOCK_STEP,
        frozen + 2 * EVIDENCE_CLOCK_STEP,
    ]


async def test_runner_evidence_after_stored_later_stamps_expect_sorted_after_them() -> (
    None
):
    """다른 시계가 더 늦은 시각으로 남긴 증거가 있어도 새 증거는 그 뒤로 정렬된다."""
    ahead = datetime.now(UTC) + timedelta(days=1)
    evidence = FakeEvidenceRepository()
    for number, created_at in (
        (1, None),
        (2, ahead.replace(tzinfo=None)),
        (3, ahead - timedelta(hours=1)),
    ):
        evidence.append(
            AgentEvidence(
                id=f"run-1:evidence:{number}",
                agent_state_id="run-1",
                kind=AgentEvidenceKind.SIGNAL,
                created_at=created_at,
            )
        )

    await _collect(
        _runner(FakeStateRepository(), evidence),
        RunAgentInput(state_id="run-1", instruction="go"),
    )

    appended = evidence.list_by_state("run-1")[3:]
    stamps = [item.created_at for item in appended if item.created_at is not None]
    assert len(stamps) == len(appended) > 1
    assert stamps[0] == ahead + EVIDENCE_CLOCK_STEP
    assert all(earlier < later for earlier, later in zip(stamps, stamps[1:]))
