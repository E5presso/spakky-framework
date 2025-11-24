"""String casing conversion utilities.

Provides utilities for converting between different string casing formats
commonly used in CLI applications.
"""

import re

PATTERN: re.Pattern[str] = re.compile(r"(?<!^)(?=[A-Z])")


def pascal_to_kebab(pascal_case: str) -> str:
    """Convert PascalCase string to kebab-case.

    Args:
        pascal_case: A string in PascalCase format.

    Returns:
        The string converted to kebab-case format.

    Example:
        >>> pascal_to_kebab("UserController")
        'user-controller'
    """
    return PATTERN.sub("-", pascal_case).lower()
