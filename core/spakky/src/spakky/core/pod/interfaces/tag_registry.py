from abc import ABC, abstractmethod
from typing import Callable

from spakky.core.pod.annotations.tag import Tag


class ITagRegistry(ABC):
    @property
    @abstractmethod
    def tags(self) -> frozenset[Tag]: ...

    @abstractmethod
    def register_tag(self, tag: Tag) -> None: ...

    @abstractmethod
    def contains_tag(self, tag: Tag) -> bool: ...

    @abstractmethod
    def list_tags(
        self, selector: Callable[[Tag], bool] | None = None
    ) -> frozenset[Tag]: ...
