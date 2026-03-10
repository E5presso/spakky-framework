"""Metadata extraction utilities for Annotated types.

This module provides utilities for extracting metadata from Python's Annotated type hints.
"""

from abc import ABC
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    ClassVar,
    Self,
    TypeAlias,
    TypeGuard,
    get_args,
    get_origin,
)

from spakky.core.common.error import AbstractSpakkyFrameworkError

AnnotatedType: TypeAlias = Annotated[type[Any], ...]


class MetadataNotFoundError(AbstractSpakkyFrameworkError):
    """Raised when expected metadata is not found in an Annotated type."""

    message: ClassVar[str] = "Expected metadata not found in Annotated type."


class InvalidAnnotatedTypeError(AbstractSpakkyFrameworkError):
    """Raised when an invalid Annotated type is provided."""

    message: ClassVar[str] = "Provided type is not a valid Annotated type."


@dataclass
class AbstractMetadata(ABC):
    """Abstract base class for type metadata."""

    @staticmethod
    def _validate_annotated(annotated: AnnotatedType) -> TypeGuard[AnnotatedType]:
        """Validate that the provided type is an Annotated type.

        Args:
            annotated (Annotated[type[Any], ...]): The Annotated type to validate.
        Raises:
            InvalidAnnotatedTypeError: If the provided type is not Annotated.
        """
        if get_origin(annotated) is not Annotated:
            return False
        return True

    @classmethod
    def get_actual_type(cls, annotated: AnnotatedType) -> type[Any]:
        """Get the actual Python type from the Annotated type.

        Args:
            annotated (AnnotatedType): The Annotated type to extract the actual type from.

        Returns:
            type[Any]: The actual Python type.
        """
        if not cls._validate_annotated(annotated):
            raise InvalidAnnotatedTypeError
        return annotated.__origin__

    @classmethod
    def all(cls, annotated: AnnotatedType) -> list[Self]:
        """Get all metadata of this type from the Annotated type.

        Args:
            annotated (AnnotatedType): The Annotated type to extract metadata from.

        Returns:
            list[Self]: List of metadata instances of this type.
        """
        if not cls._validate_annotated(annotated):
            return []
        metadatas = get_args(annotated)
        return [data for data in metadatas if isinstance(data, cls)]

    @classmethod
    def get(cls, annotated: AnnotatedType) -> Self:
        """Get a single metadata of this type from the Annotated type.

        Args:
            annotated (AnnotatedType): The Annotated type to extract metadata from.
        Returns:
            Self: The metadata instance of this type.
        """
        if not cls._validate_annotated(annotated):
            raise InvalidAnnotatedTypeError
        metadatas = get_args(annotated)
        found = next(iter(data for data in metadatas if isinstance(data, cls)), None)
        if found is None:
            raise MetadataNotFoundError
        return found

    @classmethod
    def get_or_none(cls, annotated: AnnotatedType) -> Self | None:
        """Get a single metadata of this type from the Annotated type, or None if not found.

        Args:
            annotated (AnnotatedType): The Annotated type to extract metadata from.

        Returns:
            Self | None: The metadata instance of this type, or None if not found.
        """
        if not cls._validate_annotated(annotated):
            return None
        metadatas = get_args(annotated)
        return next(iter(data for data in metadatas if isinstance(data, cls)), None)

    @classmethod
    def get_or_default(cls, annotated: AnnotatedType, default: Self) -> Self:
        """Get a single metadata of this type from the Annotated type, or a default if not found.

        Args:
            annotated (AnnotatedType): The Annotated type to extract metadata from.
            default (Self): The default metadata to return if not found.

        Returns:
            Self: The metadata instance of this type, or the default if not found.
        """
        if not cls._validate_annotated(annotated):
            return default
        metadatas = get_args(annotated)
        return next(
            iter(data for data in metadatas if isinstance(data, cls)),
            default,
        )

    @classmethod
    def exists(cls, annotated: AnnotatedType) -> bool:
        """Check if metadata of this type exists in the Annotated type.

        Args:
            annotated (AnnotatedType): The Annotated type to check.

        Returns:
            bool: True if metadata of this type exists, False otherwise.
        """
        if not cls._validate_annotated(annotated):
            return False
        metadatas = get_args(annotated)
        return any(isinstance(data, cls) for data in metadatas)
