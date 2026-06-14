from abc import ABC, abstractmethod


class IEquatable(ABC):
    """Interface for equatable objects."""

    @abstractmethod
    def __eq__(self, __value: object) -> bool:
        """Checks equality with another object.

        Args:
            __value (object): The object to compare with.

        Returns:
            bool: True if equal, False otherwise.
        """

    @abstractmethod
    def __hash__(self) -> int:
        """Returns the hash of the object.

        Returns:
            int: The hash value.
        """
