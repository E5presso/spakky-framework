from typing import Protocol, Self, TypeVar, runtime_checkable


@runtime_checkable
class ICloneable(Protocol):
    """Interface for cloneable objects."""

    def clone(self) -> Self:
        """Creates a clone of the current object.

        Returns:
            Self: A new instance that is a clone of the current object.
        """
        ...


CloneableT = TypeVar("CloneableT", bound=ICloneable)
CloneableT_co = TypeVar("CloneableT_co", bound=ICloneable, covariant=True)
CloneableT_contra = TypeVar("CloneableT_contra", bound=ICloneable, contravariant=True)
