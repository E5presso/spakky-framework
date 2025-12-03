"""Metadata for qualifying dependency injection.

This module provides the Qualifier class for creating custom
dependency qualifiers in Annotated type hints.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from spakky.core.metadata import AbstractMetadata

if TYPE_CHECKING:
    from spakky.pod.annotations.pod import Pod


@dataclass
class Qualifier(AbstractMetadata):
    """Metadata for qualifying which Pod to inject.

    Used in Annotated type hints to select specific Pods when
    multiple candidates exist.

    Example:
        @Pod()
        class Service:
            def __init__(
                self,
                repo: Annotated[IRepo, Qualifier(lambda p: p.name == "primary")],
            ) -> None:
                self.repo = repo
    """

    selector: Callable[["Pod"], bool]
    """Predicate function to filter Pod candidates."""

    def __post_init__(self) -> None:
        """Validate that selector is callable.

        Raises:
            TypeError: If selector is not callable.
        """
        if not callable(self.selector):
            raise TypeError(
                f"Qualifier selector must be callable, "
                f"got {type(self.selector).__name__}"
            )
