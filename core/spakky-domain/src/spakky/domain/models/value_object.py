"""Value object model for domain-driven design.

This module provides AbstractValueObject for representing immutable domain concepts
compared by their attributes rather than identity.
"""

from abc import ABC
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from functools import cache
from typing import Final, Self, override
from uuid import UUID

from spakky.core.common.interfaces.cloneable import ICloneable
from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import IDataclass, immutable

from spakky.domain.error import AbstractSpakkyDomainError
from spakky.domain.models.base import AbstractDomainModel


class UnhashableFieldTypeError(AbstractSpakkyDomainError):
    """Raised when a value object field type is not hashable."""

    message = "Value object field type is not hashable."
    field_name: str

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name
        super().__init__(self.message)


_SCALAR_TYPES: Final[frozenset[type]] = frozenset(
    {str, int, float, bool, bytes, complex, type(None), Decimal, UUID}
    | {date, datetime, time, timedelta}
)
"""Leaf types that ``dataclasses.astuple`` would only copy, never restructure."""


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

    def validate(self) -> None:
        """Validate value object state.

        Subclasses may override this method to enforce value object invariants.
        """
        return

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
        return self._comparison_key() == __value._comparison_key()

    @override
    def __hash__(self) -> int:
        """Compute hash from all hashable attributes.

        Returns:
            Hash of tuple containing all attributes (order-preserving).
        """
        return hash(self._comparison_key())

    def _comparison_key(self) -> tuple[object, ...]:
        """Return this value object's field values as a structural tuple.

        This matches ``dataclasses.astuple`` for equality and hashing (nested
        dataclasses become tuples; list, tuple and dict containers keep their
        type) but never deep-copies, so one comparison costs no object copies.
        """
        return AbstractValueObject._structural_tuple(
            self, AbstractValueObject._field_names(type(self))
        )

    @staticmethod
    @cache
    def _field_names(dataclass_type: type) -> tuple[str, ...]:
        # Field layout is fixed once a dataclass is created; cache it per type.
        return tuple(field.name for field in fields(dataclass_type))

    @staticmethod
    def _structural_tuple(
        instance: object, field_names: tuple[str, ...]
    ) -> tuple[object, ...]:
        return tuple(
            AbstractValueObject._structural_value(
                getattr(instance, name)  # dataclass field by name; slots lack __dict__
            )
            for name in field_names
        )

    @staticmethod
    def _structural_value(value: object) -> object:
        value_type = type(value)
        if value_type in _SCALAR_TYPES or isinstance(value, Enum):
            return value
        if is_dataclass(value) and not isinstance(value, type):
            return AbstractValueObject._structural_tuple(
                value, AbstractValueObject._field_names(value_type)
            )
        if isinstance(value, list):
            return [AbstractValueObject._structural_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(AbstractValueObject._structural_value(item) for item in value)
        if isinstance(value, dict):
            return {
                AbstractValueObject._structural_value(
                    key
                ): AbstractValueObject._structural_value(item)
                for key, item in value.items()
            }
        return value

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
            # typing 별칭/제네릭 타입은 __hash__ 속성이 없을 수 있어 안전 조회
            if getattr(type, "__hash__", None) is None:  # hashability protocol check
                raise UnhashableFieldTypeError(name)
