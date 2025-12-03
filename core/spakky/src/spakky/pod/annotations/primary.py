"""Annotation for marking preferred Pod implementation.

This module provides the @Primary annotation to indicate the preferred
implementation when multiple Pods of the same type exist.
"""

from dataclasses import dataclass

from spakky.core.annotation import ClassAnnotation


@dataclass
class Primary(ClassAnnotation):
    """Mark a Pod as the primary implementation.

    When multiple Pods match a dependency type, the one marked with @Primary
    is selected by default without requiring explicit qualification.
    """

    ...
