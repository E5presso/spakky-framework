"""Utilities for creating mutable and immutable dataclasses.

This module provides decorators that create dataclasses with predefined mutability settings.
"""

from dataclasses import dataclass, field
from typing import dataclass_transform

from spakky.core.types import AnyT


@dataclass_transform(
    eq_default=False,
    kw_only_default=True,
    frozen_default=False,
    field_specifiers=(field,),
)
def mutable(cls: type[AnyT]) -> type[AnyT]:
    """Decorator to create a mutable dataclass with keyword-only arguments.

    Args:
        cls: The class to transform into a mutable dataclass.

    Returns:
        type[AnyT]: A mutable dataclass with frozen=False, kw_only=True, eq=False.
    """
    return dataclass(frozen=False, kw_only=True, eq=False)(cls)


@dataclass_transform(
    eq_default=False,
    kw_only_default=True,
    frozen_default=True,
    field_specifiers=(field,),
)
def immutable(cls: type[AnyT]) -> type[AnyT]:
    """Decorator to create an immutable dataclass with keyword-only arguments.

    Args:
        cls: The class to transform into an immutable dataclass.

    Returns:
        type[AnyT]: An immutable dataclass with frozen=True, kw_only=True, eq=False.
    """
    return dataclass(frozen=True, kw_only=True, eq=False)(cls)
