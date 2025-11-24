"""Transactional aspect for automatic database transaction management.

This module provides @Transactional annotation and corresponding aspects
for automatic transaction begin/commit/rollback.
"""

from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Any

from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import Around
from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import AsyncFunc, Func
from spakky.domain.ports.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.pod.annotations.order import Order


@dataclass
class Transactional(FunctionAnnotation):
    """Annotation for enabling automatic transaction management.

    Methods decorated with @Transactional() will execute within a transaction
    that automatically commits on success or rolls back on exception.
    """

    ...


@Order(0)
@AsyncAspect()
class AsyncTransactionalAspect(IAsyncAspect):
    """Aspect for managing transactions around async methods.

    Wraps async methods decorated with @Transactional in a transaction context,
    automatically committing on success or rolling back on exception.
    """

    __transacntion: AbstractAsyncTransaction

    def __init__(self, transaction: AbstractAsyncTransaction) -> None:
        """Initialize async transactional aspect.

        Args:
            transaction: Transaction manager for async operations.
        """
        super().__init__()
        self.__transacntion = transaction

    @Around(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute async method within transaction context.

        Args:
            joinpoint: The async method being intercepted.
            *args: Positional arguments to the method.
            **kwargs: Keyword arguments to the method.

        Returns:
            The result of the method execution.

        Raises:
            Exception: Re-raises any exception after rolling back transaction.
        """
        try:
            async with self.__transacntion:
                result = await joinpoint(*args, **kwargs)
        except:
            raise
        return result


@Order(0)
@Aspect()
class TransactionalAspect(IAspect):
    """Aspect for managing transactions around synchronous methods.

    Wraps sync methods decorated with @Transactional in a transaction context,
    automatically committing on success or rolling back on exception.
    """

    __transaction: AbstractTransaction

    def __init__(self, transaction: AbstractTransaction) -> None:
        """Initialize sync transactional aspect.

        Args:
            transaction: Transaction manager for sync operations.
        """
        super().__init__()
        self.__transaction = transaction

    @Around(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        """Execute sync method within transaction context.

        Args:
            joinpoint: The sync method being intercepted.
            *args: Positional arguments to the method.
            **kwargs: Keyword arguments to the method.

        Returns:
            The result of the method execution.

        Raises:
            Exception: Re-raises any exception after rolling back transaction.
        """
        try:
            with self.__transaction:
                result = joinpoint(*args, **kwargs)
        except:
            raise
        return result
