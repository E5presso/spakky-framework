from abc import ABC, abstractmethod
from typing import Self


class ICloneable(ABC):
    """Interface for cloneable objects."""

    @abstractmethod
    def clone(self) -> Self:
        """Creates a clone of the current object.

        Returns:
            Self: A new instance that is a clone of the current object.
        """
