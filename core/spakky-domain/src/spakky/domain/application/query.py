"""Query pattern abstractions for CQRS.

This module provides base classes and protocols for implementing
query use cases in CQRS architecture.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable

from spakky.core.common.mutability import immutable


@immutable
class AbstractQuery(ABC):
    """Base class for query DTOs.

    Queries represent intent to read system state without modification.
    """

    ...


class IQueryUseCase[QueryT_contra: AbstractQuery, ResultT_co](ABC):
    """Interface for synchronous query use cases."""

    @abstractmethod
    def run(self, query: QueryT_contra) -> ResultT_co:
        """Execute query and return result.

        Args:
            query: The query to execute.

        Returns:
            Query result.
        """
        ...


class IAsyncQueryUseCase[QueryT_contra: AbstractQuery, ResultT_co](ABC):
    """Interface for asynchronous query use cases."""

    @abstractmethod
    def run(self, query: QueryT_contra) -> Awaitable[ResultT_co]:
        """Execute query asynchronously and return result.

        The declaration uses ``Awaitable[ResultT_co]`` instead of
        ``async def`` so that the covariant ``ResultT_co`` remains sound
        under pyrefly's variance analysis. Concrete implementations may
        still use ``async def run`` because ``Coroutine`` is a subtype of
        ``Awaitable``.

        Args:
            query: The query to execute.

        Returns:
            Awaitable resolving to the query result.
        """
        ...
