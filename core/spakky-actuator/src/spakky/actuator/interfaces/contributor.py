"""Info contributor extension points."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class IInfoContributor(ABC):
    """Synchronous contributor for actuator info output."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable contributor name used for deterministic merge ordering."""
        ...

    @abstractmethod
    def contribute_info(self) -> Mapping[str, object]:
        """Return info entries contributed by this extension."""
        ...


class IAsyncInfoContributor(ABC):
    """Asynchronous contributor for actuator info output."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable contributor name used for deterministic merge ordering."""
        ...

    @abstractmethod
    async def contribute_info_async(self) -> Mapping[str, object]:
        """Return info entries contributed by this extension."""
        ...
