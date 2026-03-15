from abc import ABC, abstractmethod
from typing import Generic, Sequence, TypeVar

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import immutable

ProxyIdT_contra = TypeVar("ProxyIdT_contra", bound=IEquatable, contravariant=True)


@immutable
class ProxyModel(IEquatable, Generic[ProxyIdT_contra]):
    """Immutable read-only projection model identified by an equatable ID."""

    id: ProxyIdT_contra

    def __eq__(self, other: object) -> bool:
        """Compare by ID equality."""
        if not isinstance(other, type(self)):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash based on ID."""
        return hash(self.id)


ProxyModelT_co = TypeVar("ProxyModelT_co", bound=ProxyModel[IEquatable], covariant=True)


class IGenericProxy(ABC, Generic[ProxyModelT_co, ProxyIdT_contra]):
    """Synchronous read-only proxy interface for querying projections."""

    @abstractmethod
    def get(self, proxy_id: ProxyIdT_contra) -> ProxyModelT_co:
        """Get a proxy model by ID."""
        ...

    @abstractmethod
    def get_or_none(self, proxy_id: ProxyIdT_contra) -> ProxyModelT_co | None:
        """Get a proxy model by ID, or None if not found."""
        ...

    @abstractmethod
    def contains(self, proxy_id: ProxyIdT_contra) -> bool:
        """Check if a proxy model with the given ID exists."""
        ...

    @abstractmethod
    def range(self, proxy_ids: Sequence[ProxyIdT_contra]) -> Sequence[ProxyModelT_co]:
        """Get multiple proxy models by their IDs."""
        ...


class IAsyncGenericProxy(ABC, Generic[ProxyModelT_co, ProxyIdT_contra]):
    """Asynchronous read-only proxy interface for querying projections."""

    @abstractmethod
    async def get(self, proxy_id: ProxyIdT_contra) -> ProxyModelT_co:
        """Get a proxy model by ID."""
        ...

    @abstractmethod
    async def get_or_none(self, proxy_id: ProxyIdT_contra) -> ProxyModelT_co | None:
        """Get a proxy model by ID, or None if not found."""
        ...

    @abstractmethod
    async def contains(self, proxy_id: ProxyIdT_contra) -> bool:
        """Check if a proxy model with the given ID exists."""
        ...

    @abstractmethod
    async def range(
        self, proxy_ids: Sequence[ProxyIdT_contra]
    ) -> Sequence[ProxyModelT_co]:
        """Get multiple proxy models by their IDs."""
        ...
