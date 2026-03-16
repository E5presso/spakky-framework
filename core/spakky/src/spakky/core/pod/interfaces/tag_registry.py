from abc import ABC, abstractmethod
from typing import Callable

from spakky.core.pod.annotations.tag import Tag


class ITagRegistry(ABC):
    """Registry for managing custom metadata tags attached to Pods."""

    @property
    @abstractmethod
    def tags(self) -> frozenset[Tag]:
        """All registered tags."""
        ...

    @abstractmethod
    def register_tag(self, tag: Tag) -> None:
        """Register a tag in the registry."""
        ...

    @abstractmethod
    def contains_tag(self, tag: Tag) -> bool:
        """Check if a tag is registered."""
        ...

    @abstractmethod
    def list_tags(
        self, selector: Callable[[Tag], bool] | None = None
    ) -> frozenset[Tag]:
        """List tags, optionally filtered by a selector predicate."""
        ...
