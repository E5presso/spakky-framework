from dataclasses import dataclass
from typing import Any, Self, final

from spakky.core.constants import ANNOTATION_METADATA
from spakky.core.error import AbstractSpakkyFrameworkError
from spakky.core.types import AnyT, ClassT, FuncT


@dataclass
class Annotation:
    """Base class for type-safely injecting metadata(annotation as said) into objects."""

    def __call__(self, obj: AnyT) -> AnyT:
        return self.__set_metadata(obj)

    @final
    def __set_metadata(self, obj: AnyT) -> AnyT:
        metadata: dict[type, list[Self]] = self.__get_metadata(obj)
        for base_type in type(self).mro():
            if base_type not in metadata:
                metadata[base_type] = []
            metadata[base_type].append(self)
        setattr(obj, ANNOTATION_METADATA, metadata)
        return obj

    @final
    @classmethod
    def __get_metadata(cls, obj: Any) -> dict[type, list[Self]]:
        metadata: dict[type, list[Self]] = getattr(obj, ANNOTATION_METADATA, {})
        return metadata

    @final
    @classmethod
    def all(cls, obj: Any) -> list[Self]:
        """Get all list of annotations from the object.

        Args:
            obj (Any): The object to get the annotations from.

        Returns:
            list[Self]: List of annotations.
        """
        metadata: dict[type, list[Self]] = cls.__get_metadata(obj)
        annotations: list[Self] = metadata.get(cls, [])
        return annotations

    @final
    @classmethod
    def get(cls, obj: Any) -> Self:
        """Get a single annotation from the object.
        Args:
            obj (Any): The object to get the annotation from.
        Returns:
            Self: The annotation.
        Raises:
            AnnotationNotFoundError: If no annotation is found.
            MultipleAnnotationFoundError: If multiple annotations are found.
        """
        metadata: dict[type, list[Self]] = cls.__get_metadata(obj)
        if cls not in metadata:
            raise AnnotationNotFoundError(cls, obj)
        annotations: list[Self] = metadata.get(cls, [])
        if len(annotations) > 1:
            raise MultipleAnnotationFoundError(cls, obj)
        return annotations[0]

    @final
    @classmethod
    def get_or_none(cls, obj: Any) -> Self | None:
        """Get a single annotation from the object or None if not found.

        Args:
            obj (Any): The object to get the annotation from.

        Raises:
            MultipleAnnotationFoundError: If multiple annotations are found.

        Returns:
            Self | None: The annotation or None if not found.
        """
        metadata: dict[type, list[Self]] = cls.__get_metadata(obj)
        if cls not in metadata:
            return None
        annotations: list[Self] = metadata.get(cls, [])
        if len(annotations) > 1:
            raise MultipleAnnotationFoundError(cls, obj)
        return annotations[0]

    @final
    @classmethod
    def get_or_default(cls, obj: Any, default: Self) -> Self:
        """Get a single annotation from the object or a default value if not found.

        Args:
            obj (Any): The object to get the annotation from.
            default (Self): The default value to return if not found.

        Raises:
            MultipleAnnotationFoundError: If multiple annotations are found.

        Returns:
            Self: The annotation or the default value if not found.
        """
        metadata: dict[type, list[Self]] = cls.__get_metadata(obj)
        if cls not in metadata:
            return default
        annotations: list[Self] = metadata.get(cls, [])
        if len(annotations) > 1:
            raise MultipleAnnotationFoundError(cls, obj)
        return annotations[0]

    @final
    @classmethod
    def exists(cls, obj: Any) -> bool:
        """Check if the annotation exists in the object.

        Args:
            obj (Any): The object to check.

        Returns:
            bool: True if the annotation exists, False otherwise.
        """
        metadata: dict[type, list[Self]] = cls.__get_metadata(obj)
        return cls in metadata


@dataclass
class ClassAnnotation(Annotation):
    """Annotation for classes.

    Args:
        Annotation (_type_): Base annotation class.
    """

    def __call__(self, obj: ClassT) -> ClassT:
        """Call method to annotate a class.

        Args:
            obj (ClassT): The class to annotate.

        Returns:
            ClassT: The annotated class.
        """
        return super().__call__(obj)


@dataclass
class FunctionAnnotation(Annotation):
    """Annotation for functions.

    Args:
        Annotation (_type_): Base annotation class.
    """

    def __call__(self, obj: FuncT) -> FuncT:
        """Call method to annotate a function.

        Args:
            obj (FuncT): The function to annotate.

        Returns:
            FuncT: The annotated function.
        """
        return super().__call__(obj)


class AnnotationNotFoundError(AbstractSpakkyFrameworkError):
    """Exception raised when no annotation is found in an object."""

    message = "Annotation not found in the object."


class MultipleAnnotationFoundError(AbstractSpakkyFrameworkError):
    """Exception raised when multiple annotations are found in an object."""

    message = "Multiple annotations found in the object."
