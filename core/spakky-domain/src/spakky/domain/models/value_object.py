"""Value object model for domain-driven design.

This module provides AbstractValueObject for representing immutable domain concepts
compared by their attributes rather than identity.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import astuple
from typing import Self

from spakky.core.common.interfaces.cloneable import ICloneable
from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import immutable


@immutable
class AbstractValueObject(IEquatable, ICloneable, ABC):
    """Base class for immutable value objects.

    Value objects represent domain concepts without identity, compared by
    their attributes. All fields must be hashable.
    """

    def clone(self) -> Self:
        """Create deep copy of this value object.

        Returns:
            Cloned value object.
        """
        return deepcopy(self)

    @abstractmethod
    def validate(self) -> None:
        """Validate value object state.

        Raises:
            AbstractDomainValidationError: If validation fails.
        """
        ...

    def __eq__(self, __value: object) -> bool:
        """Compare value objects by attributes.

        Args:
            __value: Object to compare with.

        Returns:
            True if same type and all attributes equal.
        """
        if not isinstance(__value, type(self)):
            return False
        return astuple(self) == astuple(__value)

    def __hash__(self) -> int:
        """Compute hash from all hashable attributes.

        Returns:
            Hash of tuple containing all attributes (order-preserving).
        """
        return hash(astuple(self))

    def __post_init__(self) -> None:
        """Validate value object after initialization."""
        self.validate()

    def __init_subclass__(cls) -> None:
        """Verify all attributes are hashable.

        Raises:
            TypeError: If any attribute type is not hashable.
        """
        super().__init_subclass__()
        for name, type in cls.__annotations__.items():
            if getattr(type, "__hash__", None) is None:
                raise TypeError(f"type of '{name}' is not hashable")
