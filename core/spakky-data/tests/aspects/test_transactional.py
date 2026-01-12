"""Tests for @Transactional annotation and TransactionalAspect."""

from typing import Any

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


def test_transactional_aspect_commits_on_success() -> None:
    """Test that TransactionalAspect commits transaction on successful method execution."""

    @Pod()
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

    @UseCase()
    class TestUseCase:
        @Transactional()
        def execute(self) -> str:
            return "success"

    context = ApplicationContext()
    context.add(InMemoryTransaction)
    context.add(TestUseCase)
    context.add(TransactionalAspect)
    context.start()

    use_case: TestUseCase = context.get(type_=TestUseCase)
    transaction: InMemoryTransaction = context.get(type_=InMemoryTransaction)

    result = use_case.execute()

    assert result == "success"
    assert transaction.committed is True
    assert transaction.rolled_back is False


def test_transactional_aspect_rollbacks_on_error() -> None:
    """Test that TransactionalAspect rolls back transaction when method raises exception."""

    @Pod()
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

    @UseCase()
    class TestUseCase:
        @Transactional()
        def execute(self) -> str:
            raise RuntimeError("Something went wrong")

    context = ApplicationContext()
    context.add(InMemoryTransaction)
    context.add(TestUseCase)
    context.add(TransactionalAspect)
    context.start()

    use_case: TestUseCase = context.get(type_=TestUseCase)
    transaction: InMemoryTransaction = context.get(type_=InMemoryTransaction)

    with pytest.raises(RuntimeError, match="Something went wrong"):
        use_case.execute()

    assert transaction.committed is False
    assert transaction.rolled_back is True


@pytest.mark.asyncio
async def test_async_transactional_aspect_commits_on_success() -> None:
    """Test that AsyncTransactionalAspect commits transaction on successful method execution."""

    @Pod()
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

    @UseCase()
    class TestUseCase:
        @Transactional()
        async def execute(self) -> str:
            return "success"

    context = ApplicationContext()
    context.add(AsyncInMemoryTransaction)
    context.add(TestUseCase)
    context.add(AsyncTransactionalAspect)
    context.start()

    use_case: TestUseCase = context.get(type_=TestUseCase)
    transaction: AsyncInMemoryTransaction = context.get(type_=AsyncInMemoryTransaction)

    result = await use_case.execute()

    assert result == "success"
    assert transaction.committed is True
    assert transaction.rolled_back is False


@pytest.mark.asyncio
async def test_async_transactional_aspect_rollbacks_on_error() -> None:
    """Test that AsyncTransactionalAspect rolls back transaction when method raises exception."""

    @Pod()
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

    @UseCase()
    class TestUseCase:
        @Transactional()
        async def execute(self) -> str:
            raise RuntimeError("Something went wrong")

    context = ApplicationContext()
    context.add(AsyncInMemoryTransaction)
    context.add(TestUseCase)
    context.add(AsyncTransactionalAspect)
    context.start()

    use_case: TestUseCase = context.get(type_=TestUseCase)
    transaction: AsyncInMemoryTransaction = context.get(type_=AsyncInMemoryTransaction)

    with pytest.raises(RuntimeError, match="Something went wrong"):
        await use_case.execute()

    assert transaction.committed is False
    assert transaction.rolled_back is True


def test_transactional_annotation_exists() -> None:
    """Test that @Transactional annotation can be detected on methods."""

    @UseCase()
    class TestUseCase:
        @Transactional()
        def execute(self) -> str:
            return "success"

    assert Transactional.exists(TestUseCase.execute) is True


def test_transactional_aspect_only_applies_to_annotated_methods() -> None:
    """Test that TransactionalAspect only applies to methods with @Transactional annotation."""

    @Pod()
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

    @UseCase()
    class TestUseCase:
        def execute_without_annotation(self) -> str:
            return "no transaction"

        @Transactional()
        def execute_with_annotation(self) -> str:
            return "with transaction"

    context = ApplicationContext()
    context.add(InMemoryTransaction)
    context.add(TestUseCase)
    context.add(TransactionalAspect)
    context.start()

    use_case: TestUseCase = context.get(type_=TestUseCase)
    transaction: InMemoryTransaction = context.get(type_=InMemoryTransaction)

    # Method without annotation should not trigger transaction
    result1 = use_case.execute_without_annotation()
    assert result1 == "no transaction"
    assert transaction.committed is False
    assert transaction.rolled_back is False

    # Method with annotation should trigger transaction
    result2 = use_case.execute_with_annotation()
    assert result2 == "with transaction"
    assert transaction.committed is True
    assert transaction.rolled_back is False
