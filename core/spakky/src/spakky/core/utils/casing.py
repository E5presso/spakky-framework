"""String case conversion utilities.

This module provides functions for converting between PascalCase and snake_case.
"""

import re

PATTERN: re.Pattern[str] = re.compile(r"(?<!^)(?=[A-Z])")


def pascal_to_snake(pascal_case: str) -> str:
    """Convert PascalCase string to snake_case.

    Args:
        pascal_case: String in PascalCase format.

    Returns:
        String converted to snake_case.

    Example:
        >>> pascal_to_snake("UserService")
        'user_service'
    """
    return PATTERN.sub("_", pascal_case).lower()


def snake_to_pascal(snake_case: str) -> str:
    """Convert snake_case string to PascalCase.

    Args:
        snake_case: String in snake_case format.

    Returns:
        String converted to PascalCase.

    Example:
        >>> snake_to_pascal("user_service")
        'UserService'
    """
    return "".join(word.title() for word in snake_case.split("_"))
