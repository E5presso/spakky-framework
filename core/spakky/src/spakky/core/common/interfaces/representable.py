from abc import ABC, abstractmethod
from typing import TypeVar


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


RepresentableT = TypeVar("RepresentableT", bound=IRepresentable)
RepresentableT_co = TypeVar("RepresentableT_co", bound=IRepresentable, covariant=True)
RepresentableT_contra = TypeVar(
    "RepresentableT_contra", bound=IRepresentable, contravariant=True
)
