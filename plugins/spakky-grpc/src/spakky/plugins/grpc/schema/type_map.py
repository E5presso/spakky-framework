"""Python type to protobuf type mapping.

Maps Python built-in types to their corresponding protobuf
``FieldDescriptorProto`` type constants. Supports basic scalars,
nested dataclasses, ``list[T]`` (repeated), and ``Optional[T]``.
"""

import dataclasses
from types import NoneType
from typing import Union, get_args, get_origin

from google.protobuf.descriptor_pb2 import FieldDescriptorProto

from spakky.plugins.grpc.error import UnsupportedTypeError

SCALAR_TYPE_MAP: dict[type, int] = {
    str: FieldDescriptorProto.TYPE_STRING,
    int: FieldDescriptorProto.TYPE_INT64,
    float: FieldDescriptorProto.TYPE_DOUBLE,
    bool: FieldDescriptorProto.TYPE_BOOL,
    bytes: FieldDescriptorProto.TYPE_BYTES,
}
"""Mapping from Python scalar types to protobuf field type constants."""


def is_optional(python_type: type) -> bool:
    """Check whether a type is ``Optional[T]`` (i.e. ``Union[T, None]``).

    Args:
        python_type: The type to inspect.

    Returns:
        True if the type is Optional, False otherwise.
    """
    origin = get_origin(python_type)
    if origin is Union:
        args = get_args(python_type)
        return len(args) == 2 and NoneType in args
    return False


def unwrap_optional(python_type: type) -> type:
    """Extract the inner type from ``Optional[T]``.

    Args:
        python_type: An Optional type hint.

    Returns:
        The inner type T.
    """
    args = get_args(python_type)
    return next(arg for arg in args if arg is not NoneType)


def is_repeated(python_type: type) -> bool:
    """Check whether a type is ``list[T]``.

    Args:
        python_type: The type to inspect.

    Returns:
        True if the type is list[T], False otherwise.
    """
    return get_origin(python_type) is list


def unwrap_repeated(python_type: type) -> type:
    """Extract the element type from ``list[T]``.

    Args:
        python_type: A list type hint.

    Returns:
        The element type T.
    """
    args = get_args(python_type)
    return args[0]


def is_message_type(python_type: type) -> bool:
    """Check whether a type is a dataclass (maps to a protobuf message).

    Args:
        python_type: The type to inspect.

    Returns:
        True if the type is a dataclass, False otherwise.
    """
    return dataclasses.is_dataclass(python_type)


def resolve_proto_type(python_type: type) -> int:
    """Resolve a Python scalar type to a protobuf field type constant.

    Args:
        python_type: A Python scalar type.

    Returns:
        The corresponding ``FieldDescriptorProto.TYPE_*`` constant.

    Raises:
        UnsupportedTypeError: If the type is not a supported scalar.
    """
    if python_type in SCALAR_TYPE_MAP:
        return SCALAR_TYPE_MAP[python_type]
    if is_message_type(python_type):
        return FieldDescriptorProto.TYPE_MESSAGE
    raise UnsupportedTypeError(python_type)
