from abc import ABC, abstractmethod
from typing import Generic, Sequence, TypeVar

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.domain.error import AbstractSpakkyDomainError
from spakky.domain.models.aggregate_root import AggregateRootT

AggregateIdT_contra = TypeVar(
    "AggregateIdT_contra", bound=IEquatable, contravariant=True
)


class EntityNotFoundError(AbstractSpakkyDomainError):
    """Raised when an entity cannot be found by the given identifier."""

    message = "Entity not found by given id"


class VersionConflictError(AbstractSpakkyDomainError):
    """Raised when optimistic locking detects a version conflict during save."""

    message = "Version conflict detected during save operation"


class IGenericRepository(ABC, Generic[AggregateRootT, AggregateIdT_contra]):
    """Synchronous generic repository interface for aggregate persistence."""

    @abstractmethod
    def get(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT:
        """Get an aggregate by ID."""
        ...

    @abstractmethod
    def get_or_none(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT | None:
        """Get an aggregate by ID, or None if not found."""
        ...

    @abstractmethod
    def contains(self, aggregate_id: AggregateIdT_contra) -> bool:
        """Check if an aggregate with the given ID exists."""
        ...

    @abstractmethod
    def range(
        self, aggregate_ids: Sequence[AggregateIdT_contra]
    ) -> Sequence[AggregateRootT]:
        """Get multiple aggregates by their IDs."""
        ...

    @abstractmethod
    def save(self, aggregate: AggregateRootT) -> AggregateRootT:
        """Persist an aggregate and return the saved instance."""
        ...

    @abstractmethod
    def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        """Persist multiple aggregates and return the saved instances."""
        ...

    @abstractmethod
    def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        """Delete an aggregate and return the deleted instance."""
        ...

    @abstractmethod
    def delete_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        """Delete multiple aggregates and return the deleted instances."""
        ...


class IAsyncGenericRepository(ABC, Generic[AggregateRootT, AggregateIdT_contra]):
    """Asynchronous generic repository interface for aggregate persistence."""

    @abstractmethod
    async def get(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT:
        """Get an aggregate by ID."""
        ...

    @abstractmethod
    async def get_or_none(
        self, aggregate_id: AggregateIdT_contra
    ) -> AggregateRootT | None:
        """Get an aggregate by ID, or None if not found."""
        ...

    @abstractmethod
    async def contains(self, aggregate_id: AggregateIdT_contra) -> bool:
        """Check if an aggregate with the given ID exists."""
        ...

    @abstractmethod
    async def range(
        self, aggregate_ids: Sequence[AggregateIdT_contra]
    ) -> Sequence[AggregateRootT]:
        """Get multiple aggregates by their IDs."""
        ...

    @abstractmethod
    async def save(self, aggregate: AggregateRootT) -> AggregateRootT:
        """Persist an aggregate and return the saved instance."""
        ...

    @abstractmethod
    async def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        """Persist multiple aggregates and return the saved instances."""
        ...

    @abstractmethod
    async def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        """Delete an aggregate and return the deleted instance."""
        ...

    @abstractmethod
    async def delete_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        """Delete multiple aggregates and return the deleted instances."""
        ...
