"""Python type to protobuf type mapping.

Maps Python built-in types and composite types (``list``, ``Optional``,
nested ``BaseModel``) to their protobuf ``FieldDescriptorProto``
equivalents. Field-number metadata is extracted from pydantic
``BaseModel.model_fields[name].metadata`` entries carrying a
:class:`ProtoField` instance.
"""

from types import UnionType
from typing import Union, get_args, get_origin

from google.protobuf.descriptor_pb2 import FieldDescriptorProto
from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.error import (
    MissingProtoFieldAnnotationError,
    UnsupportedFieldTypeError,
)

PYTHON_TO_PROTO_TYPE: dict[type, FieldDescriptorProto.Type.ValueType] = {
    str: FieldDescriptorProto.TYPE_STRING,
    int: FieldDescriptorProto.TYPE_INT64,
    float: FieldDescriptorProto.TYPE_DOUBLE,
    bool: FieldDescriptorProto.TYPE_BOOL,
    bytes: FieldDescriptorProto.TYPE_BYTES,
}
"""Mapping of Python primitive types to protobuf field type constants."""


class ResolvedFieldType:
    """Result of resolving a Python type annotation to protobuf metadata.

    Attributes:
        proto_type: Protobuf field type constant from ``FieldDescriptorProto``.
        is_repeated: Whether the field is a repeated (list) field.
        is_optional: Whether the field is optional.
        is_message: Whether the field references a nested message type.
        message_type: The nested ``BaseModel`` type for message fields.
    """

    def __init__(
        self,
        proto_type: FieldDescriptorProto.Type.ValueType,
        *,
        is_repeated: bool = False,
        is_optional: bool = False,
        is_message: bool = False,
        message_type: type[BaseModel] | None = None,
    ) -> None:
        self.proto_type = proto_type
        self.is_repeated = is_repeated
        self.is_optional = is_optional
        self.is_message = is_message
        self.message_type = message_type


def resolve_type(annotation: object) -> ResolvedFieldType:
    """Resolve a Python type annotation to protobuf field metadata.

    Handles:
    - Primitive types (str, int, float, bool, bytes)
    - ``list[T]`` → repeated field
    - ``Optional[T]`` (``T | None``) → optional field
    - Nested ``BaseModel`` → message type

    Args:
        annotation: The Python type annotation to resolve.

    Returns:
        A ResolvedFieldType with protobuf mapping information.

    Raises:
        UnsupportedFieldTypeError: If the type cannot be mapped.
    """
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list:
        inner = args[0] if args else None
        if inner is None:  # pragma: no cover - defensive guard, list[T] always has args
            raise UnsupportedFieldTypeError(list)
        inner_resolved = _resolve_scalar(inner)
        return ResolvedFieldType(
            proto_type=inner_resolved.proto_type,
            is_repeated=True,
            is_message=inner_resolved.is_message,
            message_type=inner_resolved.message_type,
        )

    if _is_union(annotation, origin, args):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) != 1:
            raise UnsupportedFieldTypeError(type(annotation))
        inner_resolved = _resolve_scalar(non_none[0])
        return ResolvedFieldType(
            proto_type=inner_resolved.proto_type,
            is_optional=True,
            is_message=inner_resolved.is_message,
            message_type=inner_resolved.message_type,
        )

    return _resolve_scalar(annotation)


def extract_proto_field(model_type: type[BaseModel], field_name: str) -> ProtoField:
    """Extract the ``ProtoField`` metadata from a pydantic model field.

    Args:
        model_type: The ``BaseModel`` subclass to inspect.
        field_name: The name of the field.

    Returns:
        The ``ProtoField`` metadata attached to the field.

    Raises:
        MissingProtoFieldAnnotationError: If the field is absent or
            carries no ``ProtoField`` metadata.
    """
    field_info = model_type.model_fields.get(field_name)
    if field_info is None:
        raise MissingProtoFieldAnnotationError(model_type, field_name)
    for meta in field_info.metadata:
        if isinstance(meta, ProtoField):
            return meta
    raise MissingProtoFieldAnnotationError(model_type, field_name)


def _resolve_scalar(annotation: object) -> ResolvedFieldType:
    """Resolve a non-composite type to protobuf metadata.

    Args:
        annotation: A primitive type or nested ``BaseModel`` subclass.

    Returns:
        A ResolvedFieldType for the scalar.

    Raises:
        UnsupportedFieldTypeError: If the type cannot be mapped.
    """
    if isinstance(annotation, type) and annotation in PYTHON_TO_PROTO_TYPE:
        return ResolvedFieldType(proto_type=PYTHON_TO_PROTO_TYPE[annotation])
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return ResolvedFieldType(
            proto_type=FieldDescriptorProto.TYPE_MESSAGE,
            is_message=True,
            message_type=annotation,
        )
    raise UnsupportedFieldTypeError(type(annotation))


def _is_union(
    annotation: object,
    origin: object,
    args: tuple[object, ...],
) -> bool:
    """Check if a type annotation represents a union (``Optional[T]`` or ``T | None``).

    Handles both ``typing.Union`` and PEP 604 ``T | None`` syntax.

    Args:
        annotation: The original annotation (may be ``UnionType``).
        origin: The origin of the type annotation.
        args: The type arguments.

    Returns:
        True if the annotation is a union type.
    """
    if origin is Union:
        return True
    if isinstance(annotation, UnionType):
        return True
    return False
