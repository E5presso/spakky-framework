from abc import ABC, abstractmethod
from collections.abc import Sequence

from spakky.core.common.mutability import immutable


@immutable
class ProxyModel[ProxyIdT_contra]:
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


class IGenericProxy[ProxyModelT_co: ProxyModel[object], ProxyIdT_contra](ABC):
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


class IAsyncGenericProxy[ProxyModelT_co: ProxyModel[object], ProxyIdT_contra](ABC):
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
