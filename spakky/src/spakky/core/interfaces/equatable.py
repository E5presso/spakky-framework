from abc import abstractmethod
from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class IEquatable(Protocol):
    """Interface for equatable objects."""

    @abstractmethod
    def __eq__(self, __value: object) -> bool:
        """Checks equality with another object.

        Args:
            __value (object): The object to compare with.

        Returns:
            bool: True if equal, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def __hash__(self) -> int:
        """Returns the hash of the object.

        Returns:
            int: The hash value.
        """
        raise NotImplementedError


EquatableT = TypeVar("EquatableT", bound=IEquatable)
