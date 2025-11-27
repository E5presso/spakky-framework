# This module is based on proposal by https://github.com/python/typing/issues/777

"""Method Resolution Order (MRO) utilities for generic types.

This module provides utilities for computing MRO (Method Resolution Order)
for generic types, including parameterized generics like List[int] or Dict[str, Any].
"""

from typing import *  # type: ignore  # noqa: F403
from typing import (
    Any,
    Generic,
    Protocol,
    TypeGuard,
    _collect_parameters,  # pyrefly: ignore  # type: ignore
    get_args,
    get_origin,
)

from spakky.core.constants import ORIGIN_BASES, PARAMETERS
from spakky.core.types import ClassT


def _generic_mro(result: dict[type, Any], tp: Any) -> None:
    """Recursively collect generic MRO for a type.

    Internal helper function that builds the MRO by traversing the type hierarchy
    and resolving type parameters.

    Args:
        result: Dictionary to accumulate MRO results.
        tp: The type to process.
    """
    origin = get_origin(tp)
    if origin is None:
        origin = tp
    result[origin] = tp
    if hasattr(origin, ORIGIN_BASES):
        parameters = _collect_parameters(getattr(origin, ORIGIN_BASES))
        substitution = dict(zip(parameters, get_args(tp)))
        for base in origin.__orig_bases__:
            if get_origin(base) in result:
                continue
            base_parameters = getattr(base, PARAMETERS, ())
            if base_parameters:
                base = base[tuple(substitution.get(p, p) for p in base_parameters)]
            _generic_mro(result, base)


def generic_mro(tp: Any) -> list[type]:
    """Compute the Method Resolution Order for a generic type.

    Supports both regular classes and parameterized generic types (e.g., List[int]).

    Args:
        tp: The type or generic alias to compute MRO for.

    Returns:
        list[type]: The method resolution order as a list of types.

    Raises:
        TypeError: If tp is not a type or generic alias.
    """
    origin = get_origin(tp)
    if origin is None and not hasattr(tp, ORIGIN_BASES):
        if not isinstance(tp, type):
            raise TypeError(f"{tp!r} is not a type or a generic alias")
        return tp.mro()
    # sentinel value to avoid to subscript Generic and Protocol
    result = {Generic: Generic, Protocol: Protocol}
    _generic_mro(result, tp)  # type: ignore
    cls = origin if origin is not None else tp
    return list(result.get(sub_cls, sub_cls) for sub_cls in cls.__mro__)


def is_family_with(tp: Any, target: ClassT) -> TypeGuard[ClassT]:
    """Check if a type is related to a target type through its MRO.

    Args:
        tp: The type to check.
        target: The target type to look for in the MRO.

    Returns:
        TypeGuard[ClassT]: True if target is in tp's MRO, False otherwise.
    """
    return target in generic_mro(tp)
