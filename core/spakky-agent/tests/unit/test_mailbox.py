"""Unit tests for live per-run agent signal mailboxes."""

from asyncio import Event, get_running_loop, new_event_loop, wait_for
from threading import Thread

import pytest

from spakky.agent import (
    AgentRunMailbox,
    AgentSignal,
    AgentSignalKind,
    AgentSignalLane,
    AgentSignalPriority,
    InProcessAgentSignalMailbox,
)


def _signal(
    signal_id: str,
    kind: AgentSignalKind = AgentSignalKind.STEERING_INSTRUCTION,
    *,
    state_id: str = "run-1",
    priority: AgentSignalPriority = AgentSignalPriority.NORMAL,
) -> AgentSignal:
    return AgentSignal(
        id=signal_id,
        agent_state_id=state_id,
        kind=kind,
        priority=priority,
    )


@pytest.mark.parametrize(
    ("kind", "priority", "lane"),
    [
        (AgentSignalKind.CANCEL, AgentSignalPriority.NORMAL, AgentSignalLane.CONTROL),
        (
            AgentSignalKind.STEERING_INSTRUCTION,
            AgentSignalPriority.URGENT,
            AgentSignalLane.CONTROL,
        ),
        (
            AgentSignalKind.STEERING_INSTRUCTION,
            AgentSignalPriority.NORMAL,
            AgentSignalLane.STEERING,
        ),
        (
            AgentSignalKind.USER_MESSAGE,
            AgentSignalPriority.NORMAL,
            AgentSignalLane.STEERING,
        ),
    ],
)
def test_agent_signal_lane_kind_and_priority_expect_routed_lane(
    kind: AgentSignalKind,
    priority: AgentSignalPriority,
    lane: AgentSignalLane,
) -> None:
    """Cancel and urgent signals use the control lane; everything else steers."""
    assert _signal("s", kind, priority=priority).lane is lane


def test_agent_signal_default_priority_expect_normal_steering_lane() -> None:
    """Existing producers that set no priority keep the non-interrupting lane."""
    signal = AgentSignal(
        id="s", agent_state_id="run-1", kind=AgentSignalKind.STEERING_INSTRUCTION
    )

    assert signal.priority is AgentSignalPriority.NORMAL
    assert signal.lane is AgentSignalLane.STEERING


async def test_in_process_mailbox_publish_expect_only_subscribed_state_receives() -> (
    None
):
    """Publishing routes by state id and is a no-op for states without a run."""
    hub = InProcessAgentSignalMailbox()
    mailbox = hub.subscribe("run-1")

    hub.publish(_signal("other", state_id="run-2"))
    hub.publish(_signal("mine"))

    assert [signal.id for signal in mailbox.drain()] == ["mine"]
    assert mailbox.drain() == ()


async def test_in_process_mailbox_close_expect_unsubscribed_and_idempotent() -> None:
    """Closing detaches only that run, repeated close is harmless, late signals drop."""
    hub = InProcessAgentSignalMailbox()
    first = hub.subscribe("run-1")
    second = hub.subscribe("run-1")

    first.close()
    first.close()

    assert first.closed
    assert hub.subscriber_count("run-1") == 1
    hub.publish(_signal("late"))
    assert first.drain() == ()
    assert [signal.id for signal in second.drain()] == ["late"]
    second.close()
    assert hub.subscriber_count("run-1") == 0


async def test_run_mailbox_accept_expect_finished_run_and_foreign_state_rejected() -> (
    None
):
    """Delivery is checked in the loop critical section against identity and closure."""
    mailbox = AgentRunMailbox("run-1", get_running_loop())

    mailbox.deliver(_signal("foreign", state_id="run-2"))
    assert mailbox.drain() == ()
    mailbox.close()
    mailbox.deliver(_signal("after-finish"))

    assert mailbox.drain() == ()


async def test_run_mailbox_other_thread_expect_waiter_woken_on_run_loop() -> None:
    """A producer thread without a loop hands the signal over thread-safely."""
    hub = InProcessAgentSignalMailbox()
    mailbox = hub.subscribe("run-1")
    producer = Thread(target=hub.publish, args=(_signal("threaded"),))

    producer.start()
    await wait_for(mailbox.wait(), 1)
    producer.join()

    assert [signal.id for signal in mailbox.drain()] == ["threaded"]


async def test_run_mailbox_wait_control_expect_only_control_lane_wakes() -> None:
    """Ordinary steering wakes general waiters but never the control-lane waiter."""
    mailbox = AgentRunMailbox("run-1", get_running_loop())
    woke = Event()

    async def wait_control() -> None:
        await mailbox.wait_control()
        woke.set()

    waiter = get_running_loop().create_task(wait_control())
    mailbox.deliver(_signal("steer"))
    await wait_for(mailbox.wait(), 1)
    assert not woke.is_set()

    mailbox.deliver(_signal("stop", AgentSignalKind.CANCEL))
    await wait_for(waiter, 1)

    assert woke.is_set()
    assert [signal.id for signal in mailbox.drain()] == ["steer", "stop"]


async def test_run_mailbox_closed_loop_expect_delivery_left_to_ledger_replay() -> None:
    """A run whose loop already closed drops live delivery without raising."""
    closed_loop = new_event_loop()
    closed_loop.close()
    mailbox = AgentRunMailbox("run-1", closed_loop)

    mailbox.deliver(_signal("orphan"))

    assert mailbox.drain() == ()
