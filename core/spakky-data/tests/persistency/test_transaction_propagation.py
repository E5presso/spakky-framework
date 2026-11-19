"""중첩된 transaction scope의 propagation 동작을 검증한다."""

from typing import override

import pytest

from spakky.data.persistency.error import (
    TransactionNotActiveError,
    TransactionRollbackOnlyError,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
    Propagation,
)


class RecordingTransaction(AbstractTransaction):
    """physical transaction의 수명 사건을 번호와 함께 기록한다."""

    def __init__(self, autocommit: bool = True) -> None:
        super().__init__(autocommit=autocommit)
        self.events: list[str] = []
        self.opened = 0
        self.stack: list[int] = []

    @override
    def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)
        self.events.append(f"open:{self.opened}")

    @override
    def dispose(self) -> None:
        self.events.append(f"close:{self.stack.pop()}")

    @override
    def commit(self) -> None:
        self.events.append(f"commit:{self.stack[-1]}")

    @override
    def rollback(self) -> None:
        self.events.append(f"rollback:{self.stack[-1]}")


class AsyncRecordingTransaction(AbstractAsyncTransaction):
    """비동기 physical transaction의 수명 사건을 번호와 함께 기록한다."""

    def __init__(self, autocommit: bool = True) -> None:
        super().__init__(autocommit=autocommit)
        self.events: list[str] = []
        self.opened = 0
        self.stack: list[int] = []

    @override
    async def initialize(self) -> None:
        self.opened += 1
        self.stack.append(self.opened)
        self.events.append(f"open:{self.opened}")

    @override
    async def dispose(self) -> None:
        self.events.append(f"close:{self.stack.pop()}")

    @override
    async def commit(self) -> None:
        self.events.append(f"commit:{self.stack[-1]}")

    @override
    async def rollback(self) -> None:
        self.events.append(f"rollback:{self.stack[-1]}")


class InnerFailureError(Exception):
    """안쪽 scope에서 올라가는 업무 예외."""


class RollbackFailureError(Exception):
    """rollback 자체가 실패하는 상황을 흉내 낸다."""


def test_transaction_required_inside_required_expect_single_commit_by_outermost() -> (
    None
):
    """REQUIRED 안의 REQUIRED는 바깥에 합쳐져 가장 바깥에서 한 번만 commit·close한다."""
    transaction = RecordingTransaction()

    with transaction.scope():
        with transaction.scope(Propagation.REQUIRED):
            assert transaction.events == ["open:1"]
        assert transaction.events == ["open:1"]
        assert transaction.is_active

    assert transaction.events == ["open:1", "commit:1", "close:1"]
    assert not transaction.is_active


def test_transaction_plain_with_inside_with_expect_joined() -> None:
    """기존 `with transaction:` 중첩도 REQUIRED로 합쳐진다."""
    transaction = RecordingTransaction()

    with transaction:
        with transaction:
            pass

    assert transaction.events == ["open:1", "commit:1", "close:1"]


def test_transaction_joined_failure_caught_by_outer_expect_rollback_only_error() -> (
    None
):
    """합쳐진 안쪽이 실패하고 바깥이 잡으면 commit하지 않고 rollback 뒤 오류를 낸다."""
    transaction = RecordingTransaction()

    with pytest.raises(TransactionRollbackOnlyError):
        with transaction.scope():
            try:
                with transaction.scope():
                    raise InnerFailureError()
            except InnerFailureError:
                assert transaction.is_rollback_only

    assert transaction.events == ["open:1", "rollback:1", "close:1"]
    assert not transaction.is_rollback_only


def test_transaction_joined_failure_propagated_expect_rollback_with_original_error() -> (
    None
):
    """안쪽 예외가 바깥까지 올라가면 원래 예외로 끝나고 한 번 rollback한다."""
    transaction = RecordingTransaction()

    with pytest.raises(InnerFailureError):
        with transaction.scope():
            with transaction.scope():
                raise InnerFailureError()

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


def test_transaction_rollback_only_survives_later_successful_join_expect_rollback() -> (
    None
):
    """rollback 표시는 뒤이은 정상 안쪽 scope가 지우지 않는다."""
    transaction = RecordingTransaction()

    with pytest.raises(TransactionRollbackOnlyError):
        with transaction.scope():
            try:
                with transaction.scope():
                    raise InnerFailureError()
            except InnerFailureError:
                pass
            with transaction.scope():
                pass
            assert transaction.is_rollback_only

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


def test_transaction_requires_new_inside_required_expect_separate_commit() -> None:
    """REQUIRES_NEW는 새 physical transaction을 열고 따로 commit한 뒤 바깥으로 돌아간다."""
    transaction = RecordingTransaction()

    with transaction.scope():
        with transaction.scope(Propagation.REQUIRES_NEW):
            pass
        assert transaction.events == ["open:1", "open:2", "commit:2", "close:2"]

    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


def test_transaction_requires_new_failure_caught_expect_outer_still_commits() -> None:
    """REQUIRES_NEW 안쪽의 실패는 그 transaction만 rollback하고 바깥은 commit한다."""
    transaction = RecordingTransaction()

    with transaction.scope():
        try:
            with transaction.scope(Propagation.REQUIRES_NEW):
                raise InnerFailureError()
        except InnerFailureError:
            assert not transaction.is_rollback_only

    assert transaction.events == [
        "open:1",
        "open:2",
        "rollback:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


def test_transaction_requires_new_without_outer_expect_same_as_required() -> None:
    """바깥이 없으면 REQUIRES_NEW도 한 번 열고 commit하고 닫는다."""
    transaction = RecordingTransaction()

    with transaction.scope(Propagation.REQUIRES_NEW):
        pass

    assert transaction.events == ["open:1", "commit:1", "close:1"]


def test_transaction_nested_without_autocommit_expect_no_commit() -> None:
    """autocommit=False이면 가장 바깥도 commit하지 않고 닫기만 한다."""
    transaction = RecordingTransaction(autocommit=False)

    with transaction.scope():
        with transaction.scope():
            pass

    assert transaction.events == ["open:1", "close:1"]


def test_transaction_rollback_failure_expect_dispose_still_called() -> None:
    """rollback이 실패해도 physical transaction은 닫혀 바깥 상태가 꼬이지 않는다."""

    class FailingRollbackTransaction(RecordingTransaction):
        @override
        def rollback(self) -> None:
            raise RollbackFailureError()

    transaction = FailingRollbackTransaction()

    with pytest.raises(RollbackFailureError):
        with transaction.scope():
            raise InnerFailureError()

    assert transaction.events == ["open:1", "close:1"]
    assert not transaction.is_active


def test_transaction_exit_without_enter_expect_not_active_error() -> None:
    """열지 않은 scope를 닫으려 하면 TransactionNotActiveError가 난다."""
    transaction = RecordingTransaction()

    with pytest.raises(TransactionNotActiveError):
        transaction.__exit__(None, None, None)


async def test_async_transaction_required_inside_required_expect_single_commit() -> (
    None
):
    """비동기 REQUIRED 중첩도 가장 바깥에서 한 번만 commit·close한다."""
    transaction = AsyncRecordingTransaction()

    async with transaction.scope():
        async with transaction:
            assert transaction.events == ["open:1"]
        assert transaction.is_active

    assert transaction.events == ["open:1", "commit:1", "close:1"]
    assert not transaction.is_active


async def test_async_transaction_joined_failure_caught_expect_rollback_only_error() -> (
    None
):
    """비동기에서도 합쳐진 안쪽의 실패를 바깥이 잡으면 rollback 뒤 오류를 낸다."""
    transaction = AsyncRecordingTransaction()

    with pytest.raises(TransactionRollbackOnlyError):
        async with transaction.scope():
            try:
                async with transaction.scope():
                    raise InnerFailureError()
            except InnerFailureError:
                assert transaction.is_rollback_only

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


async def test_async_transaction_joined_failure_propagated_expect_original_error() -> (
    None
):
    """비동기 안쪽 예외가 바깥까지 올라가면 원래 예외로 끝나고 한 번 rollback한다."""
    transaction = AsyncRecordingTransaction()

    with pytest.raises(InnerFailureError):
        async with transaction.scope():
            async with transaction.scope():
                raise InnerFailureError()

    assert transaction.events == ["open:1", "rollback:1", "close:1"]


async def test_async_transaction_requires_new_expect_separate_commit() -> None:
    """비동기 REQUIRES_NEW는 따로 열고 따로 commit한다."""
    transaction = AsyncRecordingTransaction()

    async with transaction.scope():
        async with transaction.scope(Propagation.REQUIRES_NEW):
            pass

    assert transaction.events == [
        "open:1",
        "open:2",
        "commit:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


async def test_async_transaction_requires_new_failure_expect_outer_commits() -> None:
    """비동기 REQUIRES_NEW 안쪽의 실패는 바깥 commit을 막지 않는다."""
    transaction = AsyncRecordingTransaction()

    async with transaction.scope():
        try:
            async with transaction.scope(Propagation.REQUIRES_NEW):
                raise InnerFailureError()
        except InnerFailureError:
            assert not transaction.is_rollback_only

    assert transaction.events == [
        "open:1",
        "open:2",
        "rollback:2",
        "close:2",
        "commit:1",
        "close:1",
    ]


async def test_async_transaction_rollback_failure_expect_dispose_still_called() -> None:
    """비동기 rollback이 실패해도 physical transaction은 닫힌다."""

    class FailingRollbackTransaction(AsyncRecordingTransaction):
        @override
        async def rollback(self) -> None:
            raise RollbackFailureError()

    transaction = FailingRollbackTransaction()

    with pytest.raises(RollbackFailureError):
        async with transaction.scope():
            raise InnerFailureError()

    assert transaction.events == ["open:1", "close:1"]
    assert not transaction.is_active


async def test_async_transaction_exit_without_enter_expect_not_active_error() -> None:
    """비동기에서도 열지 않은 scope를 닫으면 TransactionNotActiveError가 난다."""
    transaction = AsyncRecordingTransaction()

    with pytest.raises(TransactionNotActiveError):
        await transaction.__aexit__(None, None, None)
