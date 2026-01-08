from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order

from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


@dataclass
class Transactional(FunctionAnnotation):
    """Annotation for marking methods as transactional.

    Methods decorated with @Transactional() will be executed within a transaction
    context, ensuring atomicity of operations.
    """

    pass


@Order(0)
@AsyncAspect()
class AsyncTransactionalAspect(IAsyncAspect):
    """Aspect for managing transactions in async methods.

    Intercepts async methods decorated with @Transactional and ensures that
    they are executed within a transaction context.
    """

    _transaction: AbstractAsyncTransaction

    def __init__(self, transaction: AbstractAsyncTransaction) -> None:
        self._transaction = transaction

    @Around(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        async with self._transaction:
            return await joinpoint(*args, **kwargs)


@Order(0)
@Aspect()
class TransactionalAspect(IAspect):
    """Aspect for managing transactions in sync methods.

    Intercepts sync methods decorated with @Transactional and ensures that
    they are executed within a transaction context.
    """

    _transaction: AbstractTransaction

    def __init__(self, transaction: AbstractTransaction) -> None:
        self._transaction = transaction

    @Around(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        with self._transaction:
            return joinpoint(*args, **kwargs)
