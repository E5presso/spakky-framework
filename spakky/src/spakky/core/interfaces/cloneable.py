from abc import abstractmethod
from typing import Protocol, Self, TypeVar, runtime_checkable


@runtime_checkable
class ICloneable(Protocol):
    """Interface for cloneable objects."""

    @abstractmethod
    def clone(self) -> Self:
        """Creates a clone of the current object.

        Returns:
            Self: A new instance that is a clone of the current object.
        """
        raise NotImplementedError


CloneableT = TypeVar("CloneableT", bound=ICloneable)
