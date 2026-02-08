"""Python naming convention utilities.

This module provides functions for checking Python naming conventions,
such as identifying public/private identifiers.
"""

PRIVATE_PREFIX = "_"
"""Prefix for private identifiers in Python naming convention."""

DUNDER_PREFIX = "__"
"""Prefix and suffix for magic/dunder methods."""


def is_dunder_name(name: str) -> bool:
    """Check if a name is a magic/dunder method name.

    Dunder (double underscore) names like __init__, __str__ are special
    methods that are considered public in Python.

    Args:
        name: The identifier name to check.

    Returns:
        True if the name is a dunder name (starts and ends with __).

    Example:
        >>> is_dunder_name("__init__")
        True
        >>> is_dunder_name("__str__")
        True
        >>> is_dunder_name("__private")
        False
    """
    return (
        name.startswith(DUNDER_PREFIX)
        and name.endswith(DUNDER_PREFIX)
        and len(name) > 4  # noqa: PLR2004
    )


def is_public_name(name: str) -> bool:
    """Check if a name follows public naming convention.

    In Python:
    - Names starting with underscore are private (e.g., _internal)
    - Names with double underscore prefix are name-mangled (e.g., __private)
    - Dunder names (__init__, __str__) are public magic methods

    Args:
        name: The identifier name to check.

    Returns:
        True if the name is public.

    Example:
        >>> is_public_name("username")
        True
        >>> is_public_name("__init__")
        True
        >>> is_public_name("_internal")
        False
        >>> is_public_name("__private")
        False
    """
    if is_dunder_name(name):
        return True
    return not name.startswith(PRIVATE_PREFIX)


def is_private_name(name: str) -> bool:
    """Check if a name follows private naming convention.

    In Python, names starting with underscore are considered private,
    except for dunder names which are public magic methods.

    Args:
        name: The identifier name to check.

    Returns:
        True if the name is private.

    Example:
        >>> is_private_name("_internal")
        True
        >>> is_private_name("__mangled")
        True
        >>> is_private_name("__init__")
        False
        >>> is_private_name("public")
        False
    """
    return not is_public_name(name)
