"""TransactionSynchronization의 transaction 단위 after-commit frame을 검증한다."""

import asyncio

import pytest

from spakky.data.persistency.error import TransactionSynchronizationNotOpenError
from spakky.data.persistency.transaction import PhysicalTransaction
from spakky.data.persistency.transaction_synchronization import (
    TransactionSynchronization,
)


def test_synchronization_register_without_transaction_expect_not_open_error() -> None:
    """transaction이 없을 때 작업을 걸면 기다릴 commit이 없으므로 오류가 난다."""
    synchronization = TransactionSynchronization()

    with pytest.raises(TransactionSynchronizationNotOpenError):
        synchronization.register_after_commit(lambda: None)


def test_synchronization_same_callback_twice_expect_runs_once() -> None:
    """한 transaction에서 같은 작업을 두 번 걸어도 한 번만 돈다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []

    def callback() -> None:
        calls.append("called")

    synchronization.begin_transaction(PhysicalTransaction())
    synchronization.register_after_commit(callback)
    synchronization.register_after_commit(callback)
    synchronization.commit_transaction()

    assert calls == ["called"]


def test_synchronization_nested_frame_expect_isolated_from_outer() -> None:
    """새 transaction frame의 작업은 그 frame의 commit에서만 돈다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []

    synchronization.begin_transaction(PhysicalTransaction())
    synchronization.register_after_commit(lambda: calls.append("outer"))
    synchronization.begin_transaction(PhysicalTransaction())
    synchronization.register_after_commit(lambda: calls.append("inner"))
    synchronization.commit_transaction()
    assert calls == ["inner"]
    assert synchronization.is_active

    synchronization.discard_transaction()

    assert calls == ["inner"]
    assert not synchronization.is_active


def test_synchronization_joined_scope_expect_registers_into_joined_frame() -> None:
    """합쳐진 scope의 작업은 합쳐진 transaction의 frame에 걸려 그 commit에서 돈다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []
    outer = PhysicalTransaction()

    synchronization.begin_transaction(outer)
    synchronization.join_transaction(outer)
    synchronization.register_after_commit(lambda: calls.append("joined"))
    synchronization.leave_transaction()
    assert calls == []

    synchronization.commit_transaction()

    assert calls == ["joined"]


def test_synchronization_join_unknown_transaction_expect_enclosing_frame() -> None:
    """@Transactional 없이 열린 transaction에 합쳐지면 바깥 scope의 frame에 건다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []

    synchronization.begin_transaction(PhysicalTransaction())
    synchronization.join_transaction(PhysicalTransaction())
    synchronization.register_after_commit(lambda: calls.append("joined"))
    synchronization.leave_transaction()
    synchronization.commit_transaction()

    assert calls == ["joined"]


def test_synchronization_join_without_any_frame_expect_inactive() -> None:
    """@Transactional 없이 열린 transaction에만 합쳐졌으면 작업을 걸 곳이 없다."""
    synchronization = TransactionSynchronization()

    synchronization.join_transaction(PhysicalTransaction())

    assert not synchronization.is_active
    with pytest.raises(TransactionSynchronizationNotOpenError):
        synchronization.commit_transaction()
    synchronization.leave_transaction()


async def test_synchronization_child_task_register_expect_runs_on_parent_commit() -> (
    None
):
    """transaction 안에서 띄운 자식 task가 건 작업도 부모 transaction의 commit에서 돈다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []

    async def child() -> None:
        synchronization.register_after_commit(lambda: calls.append("child"))

    synchronization.begin_transaction(PhysicalTransaction())
    await asyncio.gather(child())
    assert calls == []

    synchronization.commit_transaction()

    assert calls == ["child"]


async def test_synchronization_child_after_parent_finished_expect_inactive() -> None:
    """부모 transaction이 끝난 뒤 도는 fire-and-forget 자식에게는 작업을 걸 곳이 없다."""
    synchronization = TransactionSynchronization()
    calls: list[str] = []
    release = asyncio.Event()
    seen: list[bool] = []
    transaction = PhysicalTransaction()

    async def child() -> None:
        await release.wait()
        seen.append(synchronization.is_active)
        with pytest.raises(TransactionSynchronizationNotOpenError):
            synchronization.register_after_commit(lambda: calls.append("late"))

    synchronization.begin_transaction(transaction)
    task = asyncio.create_task(child())
    transaction.finished = True
    synchronization.commit_transaction()
    release.set()
    await task

    assert seen == [False]
    assert calls == []


async def test_synchronization_child_releasing_parent_frame_expect_not_open_error() -> (
    None
):
    """자식이 이미 넘겨진 부모 frame을 다시 닫으려 하면 오류가 난다."""
    synchronization = TransactionSynchronization()
    release = asyncio.Event()
    transaction = PhysicalTransaction()

    async def child() -> None:
        await release.wait()
        with pytest.raises(TransactionSynchronizationNotOpenError):
            synchronization.discard_transaction()

    synchronization.begin_transaction(transaction)
    task = asyncio.create_task(child())
    transaction.finished = True
    synchronization.commit_transaction()
    release.set()
    await task

    assert not synchronization.is_active


def test_synchronization_commit_without_begin_expect_not_open_error() -> None:
    """열지 않은 frame을 commit하려 하면 오류가 난다."""
    synchronization = TransactionSynchronization()

    with pytest.raises(TransactionSynchronizationNotOpenError):
        synchronization.commit_transaction()


def test_synchronization_discard_without_begin_expect_not_open_error() -> None:
    """열지 않은 frame을 버리려 하면 오류가 난다."""
    synchronization = TransactionSynchronization()

    with pytest.raises(TransactionSynchronizationNotOpenError):
        synchronization.discard_transaction()


def test_synchronization_leave_without_join_expect_not_open_error() -> None:
    """합쳐지지 않은 채 떠나려 하면 오류가 난다."""
    synchronization = TransactionSynchronization()

    with pytest.raises(TransactionSynchronizationNotOpenError):
        synchronization.leave_transaction()
