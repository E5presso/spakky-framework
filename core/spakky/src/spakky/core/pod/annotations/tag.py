from dataclasses import astuple, dataclass

from spakky.core.common.annotation import Annotation
from spakky.core.common.interfaces.equatable import IEquatable


@dataclass(eq=False)
class Tag(Annotation, IEquatable):
    """Base class for custom metadata tags attached to Pods."""

    def __eq__(self, value: object) -> bool:
        """Compare tags by their dataclass field values."""
        if self is value:
            return True
        if not isinstance(value, Tag):
            return False
        return astuple(self) == astuple(value)

    def __hash__(self) -> int:
        """Hash based on dataclass field values."""
        return hash(astuple(self))
