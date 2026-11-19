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
        owner = False
        try:
            async with self._transaction.scope(propagation):
                # The scope itself tells whether it opened the physical
                # transaction or joined one, so the buffer always follows the
                # transaction the scope actually belongs to.
                frame = self._transaction.current_frame
                owner = frame.owner
                if owner:
                    self._collector.begin_transaction(frame.transaction)
                    result = await joinpoint(*args, **kwargs)
                else:
                    self._collector.join_transaction(frame.transaction)
                    try:
                        result = await joinpoint(*args, **kwargs)
                    finally:
                        self._collector.leave_transaction()
        except BaseException:
            if owner:
                self._collector.discard_transaction()
            raise
        if owner:
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
        owner = False
        try:
            with self._transaction.scope(propagation):
                # The scope itself tells whether it opened the physical
                # transaction or joined one, so the buffer always follows the
                # transaction the scope actually belongs to.
                frame = self._transaction.current_frame
                owner = frame.owner
                if owner:
                    self._collector.begin_transaction(frame.transaction)
                    result = joinpoint(*args, **kwargs)
                else:
                    self._collector.join_transaction(frame.transaction)
                    try:
                        result = joinpoint(*args, **kwargs)
                    finally:
                        self._collector.leave_transaction()
        except BaseException:
            if owner:
                self._collector.discard_transaction()
            raise
        if owner:
            # The physical transaction opened by this call has just finished:
            # committed when autocommit is enabled. This is the single
            # "after commit" point of @Transactional.
            self._collector.commit_transaction()
        return result
