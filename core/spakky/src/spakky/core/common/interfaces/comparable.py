from abc import ABC, abstractmethod
from typing import Self, TypeVar


class IComparable(ABC):
    """Interface for comparable objects."""

    @abstractmethod
    def __lt__(self, __value: Self) -> bool:
        """Less than comparison.

        Args:
            __value (Self): The value to compare against.

        Returns:
            bool: True if self is less than __value, False otherwise.
        """

    @abstractmethod
    def __le__(self, __value: Self) -> bool:
        """Less than or equal comparison.

        Args:
            __value (Self): The value to compare against.
        Returns:
            bool: True if self is less than or equal to __value, False otherwise.
        """

    @abstractmethod
    def __gt__(self, __value: Self) -> bool:
        """Greater than comparison.

        Args:
            __value (Self): The value to compare against.

        Returns:
            bool: True if self is greater than __value, False otherwise.
        """

    @abstractmethod
    def __ge__(self, __value: Self) -> bool:
        """Greater than or equal comparison.

        Args:
            __value (Self): The value to compare against.
        Returns:
            bool: True if self is greater than or equal to __value, False otherwise.
        """


ComparableT = TypeVar("ComparableT", bound=IComparable)
ComparableT_co = TypeVar("ComparableT_co", bound=IComparable, covariant=True)
ComparableT_contra = TypeVar(
    "ComparableT_contra", bound=IComparable, contravariant=True
)
