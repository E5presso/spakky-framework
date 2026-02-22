from dataclasses import astuple, dataclass

from spakky.core.common.annotation import Annotation
from spakky.core.common.interfaces.equatable import IEquatable


@dataclass(eq=False)
class Tag(Annotation, IEquatable):
    def __eq__(self, value: object) -> bool:
        if self is value:
            return True
        if not isinstance(value, Tag):
            return False
        return astuple(self) == astuple(value)

    def __hash__(self) -> int:
        return hash(astuple(self))
