from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Any
from collections.abc import Callable

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from typing import override

from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
    Propagation,
)

__all__ = [
    "AsyncTransactionalAspect",
    "Propagation",
    "Transactional",
    "TransactionalAspect",
    "transactional",
]


@dataclass
class Transactional(FunctionAnnotation):
    """Annotation for marking methods as transactional.

    Methods decorated with @Transactional() will be executed within a transaction
    context, ensuring atomicity of operations.

    With the default ``Propagation.REQUIRED`` a call made while a transaction is
    in progress joins it: only the outermost scope commits and closes the
    session, and an exception escaping a joined call marks the whole
    transaction rollback-only. ``Propagation.REQUIRES_NEW`` always runs the
    call in a separate transaction that commits on its own.
    """

    propagation: Propagation = Propagation.REQUIRED
    """How this call relates to a transaction already in progress."""


def transactional[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorator for marking methods as transactional.

    Args:
        func: The function to decorate.
    Returns:
        The decorated function with transactional annotation.
    """
    return Transactional()(func)


@Order(1)
@AsyncAspect()
class AsyncTransactionalAspect(IAsyncAspect):
    """Aspect for managing transactions in async methods.

    Intercepts async methods decorated with @Transactional and ensures that
    they are executed within a transaction context.
    """

    _transaction: AbstractAsyncTransaction
    _collector: AggregateCollector

    def __init__(
        self,
        transaction: AbstractAsyncTransaction,
        collector: AggregateCollector,
    ) -> None:
        self._transaction = transaction
        self._collector = collector

    @Around(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    @override
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        propagation = Transactional.get(joinpoint).propagation
        if self._transaction.joins(propagation):
            async with self._transaction.scope(propagation):
                return await joinpoint(*args, **kwargs)
        self._collector.begin_transaction()
        try:
            async with self._transaction.scope(propagation):
                result = await joinpoint(*args, **kwargs)
        except BaseException:
            self._collector.discard_transaction()
            raise
        # The physical transaction opened by this call has just finished:
        # committed when autocommit is enabled. This is the single
        # "after commit" point of @Transactional.
        self._collector.commit_transaction()
        return result


@Order(1)
@Aspect()
class TransactionalAspect(IAspect):
    """Aspect for managing transactions in sync methods.

    Intercepts sync methods decorated with @Transactional and ensures that
    they are executed within a transaction context.
    """

    _transaction: AbstractTransaction
    _collector: AggregateCollector

    def __init__(
        self,
        transaction: AbstractTransaction,
        collector: AggregateCollector,
    ) -> None:
        self._transaction = transaction
        self._collector = collector

    @Around(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    @override
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        propagation = Transactional.get(joinpoint).propagation
        if self._transaction.joins(propagation):
            with self._transaction.scope(propagation):
                return joinpoint(*args, **kwargs)
        self._collector.begin_transaction()
        try:
            with self._transaction.scope(propagation):
                result = joinpoint(*args, **kwargs)
        except BaseException:
            self._collector.discard_transaction()
            raise
        # The physical transaction opened by this call has just finished:
        # committed when autocommit is enabled. This is the single
        # "after commit" point of @Transactional.
        self._collector.commit_transaction()
        return result
