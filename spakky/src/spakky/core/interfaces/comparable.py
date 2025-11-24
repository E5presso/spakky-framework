from abc import abstractmethod
from typing import Protocol, Self, TypeVar, runtime_checkable


@runtime_checkable
class IComparable(Protocol):
    """Interface for comparable objects."""

    @abstractmethod
    def __lt__(self, __value: Self) -> bool:
        """Less than comparison.

        Args:
            __value (Self): The value to compare against.

        Returns:
            bool: True if self is less than __value, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def __le__(self, __value: Self) -> bool:
        """Less than or equal comparison.

        Args:
            __value (Self): The value to compare against.
        Returns:
            bool: True if self is less than or equal to __value, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def __gt__(self, __value: Self) -> bool:
        """Greater than comparison.

        Args:
            __value (Self): The value to compare against.

        Returns:
            bool: True if self is greater than __value, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def __ge__(self, __value: Self) -> bool:
        """Greater than or equal comparison.

        Args:
            __value (Self): The value to compare against.
        Returns:
            bool: True if self is greater than or equal to __value, False otherwise.
        """
        raise NotImplementedError


ComparableT = TypeVar("ComparableT", bound=IComparable)
