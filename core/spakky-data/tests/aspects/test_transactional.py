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
    transactional,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


def test_transactional_aspect_commits_on_success() -> None:
    """TransactionalAspect가 메서드 실행 성공 시 트랜잭션을 커밋하는지 검증한다."""

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
        @transactional
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
    """TransactionalAspect가 메서드에서 예외 발생 시 트랜잭션을 롤백하는지 검증한다."""

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
    """AsyncTransactionalAspect가 비동기 메서드 실행 성공 시 트랜잭션을 커밋하는지 검증한다."""

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
    """AsyncTransactionalAspect가 비동기 메서드에서 예외 발생 시 트랜잭션을 롤백하는지 검증한다."""

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
    """@Transactional 어노테이션이 메서드에서 감지될 수 있는지 검증한다."""

    @UseCase()
    class TestUseCase:
        @Transactional()
        def execute(self) -> str:
            return "success"

    assert Transactional.exists(TestUseCase.execute) is True


def test_transactional_function_decorator_marks_method_as_transactional() -> None:
    """@transactional shorthand가 @Transactional()과 동일하게 감지되는지 검증한다."""

    @UseCase()
    class TestUseCase:
        @transactional
        def execute(self) -> str:
            return "success"

    assert Transactional.exists(TestUseCase.execute) is True


def test_transactional_aspect_only_applies_to_annotated_methods() -> None:
    """TransactionalAspect가 @Transactional 어노테이션이 있는 메서드에만 적용되는지 검증한다."""

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
    assert transaction.committed
    assert not transaction.rolled_back
