"""Metadata extraction utilities for Annotated types.

This module provides utilities for extracting metadata from Python's Annotated type hints.
"""

from abc import ABC
from dataclasses import dataclass
from typing import Annotated, cast, get_args

from spakky.core.common.types import AnyT


@dataclass
class AbstractMetadata(ABC):
    """Abstract base class for type metadata."""

    ...


def get_metadata(
    annotated: Annotated[AnyT, ...],
) -> tuple[AnyT, list[AbstractMetadata]]:
    """Extract the type and metadata from an Annotated type hint.

    Args:
        annotated: An Annotated type hint containing a type and metadata.

    Returns:
        tuple[Any, list[AbstractMetadata]]: A tuple of (type, metadata_list) where metadata_list
            contains only instances of AbstractMetadata subclasses.
    """
    metadata = get_args(annotated)
    return cast(AnyT, metadata[0]), [
        data for data in metadata[1:] if isinstance(data, AbstractMetadata)
    ]
