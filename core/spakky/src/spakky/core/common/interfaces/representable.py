from abc import ABC, abstractmethod


class IRepresentable(ABC):
    """Interface for representable objects."""

    @abstractmethod
    def __str__(self) -> str:
        """Returns the string representation of the object.

        Returns:
            str: The string representation.
        """

    @abstractmethod
    def __repr__(self) -> str:
        """Returns the official string representation of the object.

        Returns:
            str: The official string representation.
        """
