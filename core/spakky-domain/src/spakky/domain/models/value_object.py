"""Value object model for domain-driven design.

This module provides AbstractValueObject for representing immutable domain concepts
compared by their attributes rather than identity.
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import astuple
from typing import Self

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from spakky.core.common.interfaces.cloneable import ICloneable
from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import IDataclass, immutable

from spakky.domain.error import AbstractSpakkyDomainError
from spakky.domain.models.base import AbstractDomainModel


class UnhashableFieldTypeError(AbstractSpakkyDomainError):
    """Raised when a value object field type is not hashable."""

    message = "Value object field type is not hashable."


@immutable
class AbstractValueObject(AbstractDomainModel, IEquatable, ICloneable, IDataclass, ABC):
    """Base class for immutable value objects.

    Value objects represent domain concepts without identity, compared by
    their attributes. All fields must be hashable.
    """

    @override
    def clone(self) -> Self:
        """Create copy of this value object.

        Returns:
            Cloned value object.
        """
        return self

    @abstractmethod
    def validate(self) -> None:
        """Validate value object state.

        Raises:
            AbstractDomainValidationError: If validation fails.
        """
        ...

    @override
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

    @override
    def __hash__(self) -> int:
        """Compute hash from all hashable attributes.

        Returns:
            Hash of tuple containing all attributes (order-preserving).
        """
        return hash(astuple(self))

    @override
    def __post_init__(self) -> None:
        """Validate value object after initialization."""
        self.validate()

    @override
    def __init_subclass__(cls) -> None:
        """Verify all attributes are hashable.

        Raises:
            TypeError: If any attribute type is not hashable.
        """
        super().__init_subclass__()
        for name, type in cls.__annotations__.items():
            if getattr(type, "__hash__", None) is None:
                raise UnhashableFieldTypeError(f"type of '{name}' is not hashable")
