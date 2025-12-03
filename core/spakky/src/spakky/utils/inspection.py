"""Function and class inspection utilities.

This module provides utilities for introspecting functions and classes
to determine their characteristics.
"""

from inspect import FullArgSpec, getfullargspec, ismethod

from spakky.core.constants import INIT, PROTOCOL_INIT, SELF
from spakky.core.types import Action, Func


def is_instance_method(obj: Func) -> bool:
    """Check if a function is an instance method.

    Args:
        obj: The function to check.

    Returns:
        True if the function is an instance method (has 'self' as first parameter).
    """
    if ismethod(obj):
        return True
    spec: FullArgSpec = getfullargspec(obj)
    if len(spec.args) > 0 and spec.args[0] == SELF:
        return True
    return False


def has_default_constructor(cls: type[object]) -> bool:
    """Check if a class has a default (no-argument) constructor.

    Args:
        cls: The class to check.

    Returns:
        True if the class uses the default object.__init__ or protocol placeholder.
    """
    constructor: Action = getattr(cls, INIT)
    if constructor is object.__init__ or constructor.__name__ == PROTOCOL_INIT:
        # If the constructor is the default constructor
        # or a placeholder for the default constructor
        return True
    return False
