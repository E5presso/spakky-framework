"""Function and class inspection utilities.

This module provides utilities for introspecting functions and classes
to determine their characteristics.
"""

from inspect import FullArgSpec, getfullargspec, ismethod
from types import BuiltinFunctionType, FunctionType, MethodType

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
    """Return the fully qualified name (FQN) of an object.

    Resolution rules:
        1. If ``obj`` is a class, return ``obj.__module__ + "." + obj.__qualname__``.
        2. If ``obj`` is a function or method, return its own FQN.
        3. Otherwise, treat ``obj`` as an instance and return the FQN of ``type(obj)``.

    Args:
        obj: Class, function, method, or arbitrary instance.

    Returns:
        A dotted fully qualified name, for example:
        ``module.path.ClassName`` or ``module.path.ClassName.method_name``.

    Example:
        >>> class Foo:
        ...     def bar(self) -> None: pass
        >>> get_fully_qualified_name(Foo)
        '__main__.Foo'
        >>> get_fully_qualified_name(Foo.bar)
        '__main__.Foo.bar'
        >>> get_fully_qualified_name(Foo())
        '__main__.Foo'
    """

    if isinstance(obj, type):
        return f"{obj.__module__}.{obj.__qualname__}"

    if isinstance(obj, (FunctionType, MethodType, BuiltinFunctionType)):
        return f"{obj.__module__}.{obj.__qualname__}"

    cls = type(obj)
    return f"{cls.__module__}.{cls.__qualname__}"
