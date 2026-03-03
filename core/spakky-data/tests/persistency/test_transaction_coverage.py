"""Test transaction error cases for complete coverage."""

import pytest

from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


def test_transaction_exception_in_commit() -> None:
    """커밋 중 예외 발생 시 트랜잭션이 롤백되는지 검증한다."""

    class TestTransaction(AbstractTransaction):
        initialized = False
        disposed = False
        committed = False
        rolled_back = False

        def initialize(self) -> None:
            self.initialized = True

        def dispose(self) -> None:
            self.disposed = True

        def commit(self) -> None:
            self.committed = True
            raise RuntimeError("Commit failed")

        def rollback(self) -> None:
            self.rolled_back = True

    transaction = TestTransaction(autocommit=True)

    with pytest.raises(RuntimeError):
        with transaction:
            pass

    assert transaction.initialized
    assert transaction.committed
    assert transaction.rolled_back
    assert transaction.disposed


async def test_async_transaction_exception_in_commit() -> None:
    """비동기 커밋 중 예외 발생 시 트랜잭션이 롤백되는지 검증한다."""

    class TestAsyncTransaction(AbstractAsyncTransaction):
        initialized = False
        disposed = False
        committed = False
        rolled_back = False

        async def initialize(self) -> None:
            self.initialized = True

        async def dispose(self) -> None:
            self.disposed = True

        async def commit(self) -> None:
            self.committed = True
            raise RuntimeError("Commit failed")

        async def rollback(self) -> None:
            self.rolled_back = True

    transaction = TestAsyncTransaction(autocommit=True)

    with pytest.raises(RuntimeError):
        async with transaction:
            pass

    assert transaction.initialized
    assert transaction.committed
    assert transaction.rolled_back
    assert transaction.disposed
