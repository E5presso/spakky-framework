from typing import Any

import pytest
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


def test_tranasction_auto_commit() -> None:
    """트랜잭션의 autocommit=True 설정 시 컨텍스트 종료 후 자동 커밋되는지 검증한다."""

    class InMemoryTransaction(AbstractTransaction):
        committed: bool = False
        rolled_back: bool = False

        def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        def dispose(self) -> None: ...

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: InMemoryTransaction = InMemoryTransaction(autocommit=True)

    with transaction:
        print("do_something")

    assert transaction.committed is True
    assert transaction.rolled_back is False


def test_tranasction_manual_commit() -> None:
    """트랜잭션의 autocommit=False 설정 시 수동 커밋이 필요함을 검증한다."""

    class InMemoryTransaction(AbstractTransaction):
        committed: bool = False
        rolled_back: bool = False

        def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        def dispose(self) -> None: ...

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: InMemoryTransaction = InMemoryTransaction(autocommit=False)

    with transaction:
        print("do_something")

    assert transaction.committed is False
    assert transaction.rolled_back is False

    with transaction as tx:
        print("do_something")
        tx.commit()

    assert transaction.committed is True
    assert transaction.rolled_back is False


def test_tranasction_rollback_when_raised() -> None:
    """트랜잭션 내에서 예외 발생 시 자동 롤백되는지 검증한다."""

    class InMemoryTransaction(AbstractTransaction):
        committed: bool = False
        rolled_back: bool = False

        def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        def dispose(self) -> None: ...

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: InMemoryTransaction = InMemoryTransaction(autocommit=True)

    with pytest.raises(RuntimeError):
        with transaction:
            raise RuntimeError

    assert transaction.committed is False
    assert transaction.rolled_back is True


@pytest.mark.asyncio
async def test_async_tranasction_auto_commit() -> None:
    """비동기 트랜잭션의 autocommit=True 설정 시 컨텍스트 종료 후 자동 커밋되는지 검증한다."""

    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        committed: bool = False
        rolled_back: bool = False

        async def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        async def dispose(self) -> None: ...

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        async def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: AsyncInMemoryTransaction = AsyncInMemoryTransaction(autocommit=True)

    async with transaction:
        print("do_something")

    assert transaction.committed is True
    assert transaction.rolled_back is False


@pytest.mark.asyncio
async def test_async_tranasction_manual_commit() -> None:
    """비동기 트랜잭션의 autocommit=False 설정 시 수동 커밋이 필요함을 검증한다."""

    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        committed: bool = False
        rolled_back: bool = False

        async def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        async def dispose(self) -> None: ...

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        async def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: AsyncInMemoryTransaction = AsyncInMemoryTransaction(autocommit=False)

    async with transaction:
        print("do_something")

    assert transaction.committed is False
    assert transaction.rolled_back is False

    async with transaction as tx:
        print("do_something")
        await tx.commit()

    assert transaction.committed is True
    assert transaction.rolled_back is False


@pytest.mark.asyncio
async def test_async_tranasction_rollback_when_raised() -> None:
    """비동기 트랜잭션 내에서 예외 발생 시 자동 롤백되는지 검증한다."""

    class AsyncInMemoryTransaction(AbstractAsyncTransaction):
        committed: bool = False
        rolled_back: bool = False

        async def initialize(self) -> None:
            self.committed = False
            self.rolled_back = False

        async def dispose(self) -> None: ...

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def add(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

        async def delete(self, aggregate: AbstractAggregateRoot[Any]) -> None: ...

    transaction: AsyncInMemoryTransaction = AsyncInMemoryTransaction(autocommit=True)

    with pytest.raises(RuntimeError):
        async with transaction:
            raise RuntimeError

    assert transaction.committed is False
    assert transaction.rolled_back is True
