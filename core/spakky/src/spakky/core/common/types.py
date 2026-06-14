"""Type aliases and utility functions for the Spakky framework.

This module provides common type aliases and utility functions for working with types,
particularly for Optional/Union type handling.
"""

from inspect import getmembers_static
from functools import reduce
from operator import or_
from types import UnionType
from typing import (
    Any,
    Union,
    get_args,
    get_origin,
)
from collections.abc import Awaitable, Callable

type Class = type[object]
type Func = Callable[..., Any]
type AsyncFunc = Callable[..., Awaitable[Any]]
type Action = Callable[..., None]
type AsyncAction = Callable[..., Awaitable[None]]


def is_optional(type_: Any) -> bool:
    """Check if a type is Optional (Union with None).

    Args:
        type_: The type to check.

    Returns:
        bool: True if the type is Optional[T] or Union[T, None], False otherwise.
    """
    is_union_type: bool = get_origin(type_) in (UnionType, Union)
    includes_none: bool = type(None) in get_args(type_)
    is_union_with_none: bool = is_union_type and includes_none
    return is_union_with_none


def remove_none(type_: Any) -> Any:
    """Remove None from a Union type.

    If the type is Union[T, None], returns T.
    If the type is Union[T1, T2, ..., None], returns Union[T1, T2, ...].
    If the type is not a Union, returns it unchanged.

    Args:
        type_: The type to process.

    Returns:
        Any: The type with None removed from Union types.
    """
    origin = get_origin(type_)
    if origin in (UnionType, Union):
        args = get_args(type_)
        non_none_args = tuple(a for a in args if a is not type(None))
        if not non_none_args:  # pragma: no cover - coverage boundary
            return type(None)
        if len(non_none_args) == 1:
            return non_none_args[0]
        return reduce(or_, non_none_args)
    return type_


def get_callable_methods(obj: object) -> list[tuple[str, Callable[..., Any]]]:
    """Get callable members excluding properties.

    Uses inspect.getmembers_static() to avoid invoking descriptors during
    introspection, then retrieves bound methods only for non-property callables.

    Args:
        obj: The object to inspect.

    Returns:
        List of (name, bound_method) tuples for callable non-property members.
    """
    result: list[tuple[str, Callable[..., object]]] = []

    for name, value in getmembers_static(obj):
        if isinstance(value, property):
            continue

        try:
            actual = getattr(
                obj, name
            )  # introspection skips properties raising on access
        except Exception:  # noqa: BLE001
            continue

        if callable(actual):
            result.append((name, actual))

    return result
