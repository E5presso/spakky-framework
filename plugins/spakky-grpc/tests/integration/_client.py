"""Helpers that build gRPC callables against the code-first descriptor pool."""

from collections.abc import Callable

from google.protobuf.message import Message

from spakky.plugins.grpc.schema.registry import DescriptorRegistry


def _serialize(message: Message) -> bytes:
    """Serialise a protobuf message to its wire format."""
    return message.SerializeToString()


def serializer_for(
    registry: DescriptorRegistry, full_name: str
) -> Callable[[Message], bytes]:
    """Return a ``Message → bytes`` serialiser for the registered type.

    Accepts ``registry`` and ``full_name`` for API symmetry with
    :func:`deserializer_for`; the registry is not consulted because every
    protobuf ``Message`` knows its own descriptor.
    """
    del registry, full_name
    return _serialize


def deserializer_for(
    registry: DescriptorRegistry, full_name: str
) -> Callable[[bytes], Message]:
    """Return a ``bytes → Message`` deserialiser for the registered type."""
    message_class = registry.get_message_class(full_name)

    def _deserialize(data: bytes) -> Message:
        instance = message_class()
        instance.ParseFromString(data)
        return instance

    return _deserialize


def build_message(
    registry: DescriptorRegistry, full_name: str, **fields: object
) -> Message:
    """Instantiate a registered protobuf message with the given field values."""
    message_class = registry.get_message_class(full_name)
    instance = message_class()
    for name, value in fields.items():
        setattr(instance, name, value)  # framework 내부: protobuf 메시지 필드 동적 설정
    return instance


def field(message: Message, name: str) -> object:
    """Read *name* off a dynamic protobuf message with a single justification point.

    Protobuf message classes expose fields dynamically at runtime, so a
    direct attribute access cannot be statically type-checked.
    """
    # pyrefly: ignore - dynamic protobuf field access
    return getattr(message, name)
