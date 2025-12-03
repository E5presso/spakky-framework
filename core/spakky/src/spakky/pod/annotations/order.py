"""Annotation for controlling execution order.

This module provides the @Order annotation to control the order of
post-processor execution and aspect application.
"""

import sys
from dataclasses import dataclass, field

from spakky.core.annotation import ClassAnnotation


@dataclass
class Order(ClassAnnotation):
    """Control execution order of Pods.

    Lower order values execute first. Default is sys.maxsize (last).
    Commonly used for post-processors and aspects.
    """

    order: int = field(default=sys.maxsize)
    """Execution order priority (lower executes first)."""

    def __post_init__(self) -> None:
        """Validate order value.

        Raises:
            ValueError: If order is negative.
        """
        if self.order < 0:
            raise ValueError("Order cannot be negative")
