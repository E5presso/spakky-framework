from abc import abstractmethod
from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class IRepresentable(Protocol):
    """Interface for representable objects."""

    @abstractmethod
    def __str__(self) -> str:
        """Returns the string representation of the object.

        Returns:
            str: The string representation.
        """
        raise NotImplementedError

    @abstractmethod
    def __repr__(self) -> str:
        """Returns the official string representation of the object.

        Returns:
            str: The official string representation.
        """
        raise NotImplementedError


RepresentableT = TypeVar("RepresentableT", bound=IRepresentable)
