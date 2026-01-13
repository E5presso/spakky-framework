from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class IEquatable(Protocol):
    """Interface for equatable objects."""

    def __eq__(self, __value: object) -> bool:
        """Checks equality with another object.

        Args:
            __value (object): The object to compare with.

        Returns:
            bool: True if equal, False otherwise.
        """
        ...

    def __hash__(self) -> int:
        """Returns the hash of the object.

        Returns:
            int: The hash value.
        """
        ...


EquatableT = TypeVar("EquatableT", bound=IEquatable)
EquatableT_co = TypeVar("EquatableT_co", bound=IEquatable, covariant=True)
EquatableT_contra = TypeVar("EquatableT_contra", bound=IEquatable, contravariant=True)
