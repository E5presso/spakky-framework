"""Function and class inspection utilities.

This module provides utilities for introspecting functions and classes
to determine their characteristics.
"""

from inspect import FullArgSpec, getfullargspec, ismethod

from spakky.core.common.constants import INIT, PROTOCOL_INIT, SELF
from spakky.core.common.types import Action, Func


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


def get_fully_qualified_name(obj: object) -> str:
    """Get the fully qualified name of an object.

    Combines module path and qualified name to create a unique identifier.
    Works with functions, methods, classes, and instances.

    Args:
        obj: Any object with __module__ and __qualname__ attributes.
             For instances, uses the class's qualified name.

    Returns:
        Fully qualified name in format 'module.path.ClassName' or
        'module.path.ClassName.method_name'.

    Raises:
        AttributeError: If the object lacks __module__ or __qualname__.

    Example:
        >>> class Foo:
        ...     def bar(self): pass
        >>> get_fully_qualified_name(Foo)
        '__main__.Foo'
        >>> get_fully_qualified_name(Foo.bar)
        '__main__.Foo.bar'
        >>> get_fully_qualified_name(Foo())
        '__main__.Foo'
    """
    # For instances, use the class
    target = obj if isinstance(obj, type) or callable(obj) else type(obj)
    return f"{target.__module__}.{target.__qualname__}"
