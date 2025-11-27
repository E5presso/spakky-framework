"""Type aliases and utility functions for the Spakky framework.

This module provides common type aliases and utility functions for working with types,
particularly for Optional/Union type handling.
"""

from types import UnionType
from typing import (
    Any,
    Awaitable,
    Callable,
    ParamSpec,
    TypeAlias,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

Class: TypeAlias = type[Any]
Func: TypeAlias = Callable[..., Any]
AsyncFunc: TypeAlias = Callable[..., Awaitable[Any]]
Action: TypeAlias = Callable[..., None]
AsyncAction: TypeAlias = Callable[..., Awaitable[None]]

AnyT = TypeVar("AnyT", bound=Any)
AnyT_co = TypeVar("AnyT_co", bound=Any, covariant=True)
AnyT_contra = TypeVar("AnyT_contra", bound=Any, contravariant=True)

ObjectT = TypeVar("ObjectT", bound=object)
ObjectT_co = TypeVar("ObjectT_co", bound=object, covariant=True)
ObjectT_contra = TypeVar("ObjectT_contra", bound=object, contravariant=True)

ClassT = TypeVar("ClassT", bound=Class)
ClassT_co = TypeVar("ClassT_co", bound=Class, covariant=True)
ClassT_contra = TypeVar("ClassT_contra", bound=Class, contravariant=True)

FuncT = TypeVar("FuncT", bound=Func)
FuncT_co = TypeVar("FuncT_co", bound=Func, covariant=True)
FuncT_contra = TypeVar("FuncT_contra", bound=Func, contravariant=True)

AsyncFuncT = TypeVar("AsyncFuncT", bound=AsyncFunc)
AsyncFuncT_co = TypeVar("AsyncFuncT_co", bound=AsyncFunc, covariant=True)
AsyncFuncT_contra = TypeVar("AsyncFuncT_contra", bound=AsyncFunc, contravariant=True)

ActionT = TypeVar("ActionT", bound=Action)
ActionT_co = TypeVar("ActionT_co", bound=Action, covariant=True)
ActionT_contra = TypeVar("ActionT_contra", bound=Action, contravariant=True)

AsyncActionT = TypeVar("AsyncActionT", bound=AsyncAction)
AsyncActionT_co = TypeVar("AsyncActionT_co", bound=AsyncAction, covariant=True)
AsyncActionT_contra = TypeVar(
    "AsyncActionT_contra", bound=AsyncAction, contravariant=True
)

P = ParamSpec("P")
R = TypeVar("R")


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
        if not non_none_args:  # pragma: no cover
            return type(None)
        if len(non_none_args) == 1:
            return non_none_args[0]
        return Union[non_none_args]  # pyrefly: ignore  # type: ignore
    return type_
