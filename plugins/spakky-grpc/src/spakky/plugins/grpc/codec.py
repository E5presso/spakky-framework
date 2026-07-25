"""protobuf ↔ pydantic ``BaseModel`` translation shared by server and client.

Both the server-side generic handler and the client-side helper must encode
the wire payload identically: a mismatch between the two directions silently
drops or corrupts fields.  Keeping the translation in one module makes that
symmetry structural rather than a convention two call sites have to remember.

Every conversion routes through the ``google.protobuf.json_format`` bridge,
using the message classes compiled from the shared
:class:`~spakky.plugins.grpc.schema.registry.DescriptorRegistry` so that field
numbers always come from the same descriptor the peer uses.
"""

from collections.abc import Callable

from google.protobuf import json_format
from google.protobuf.message import Message
from pydantic import BaseModel

from spakky.plugins.grpc.schema.registry import DescriptorRegistry


def basemodel_to_protobuf(model: BaseModel, message_class: type[Message]) -> Message:
    """Convert a pydantic ``BaseModel`` instance into a protobuf ``Message``.

    The model is serialised to JSON via pydantic's v2 ``model_dump_json`` API
    and parsed into a protobuf ``Message`` by ``json_format.Parse``. ``None``
    values from optional fields are emitted as JSON ``null`` which
    ``json_format`` treats as "field unset" for proto3 optional fields.

    Args:
        model: The pydantic ``BaseModel`` instance to convert.
        message_class: The target protobuf message class.

    Returns:
        A populated protobuf ``Message``.
    """
    return json_format.Parse(
        model.model_dump_json(),
        message_class(),
        ignore_unknown_fields=False,
    )


def protobuf_to_basemodel[BaseModelT: BaseModel](
    message: Message, model_type: type[BaseModelT]
) -> BaseModelT:
    """Convert a protobuf ``Message`` into a pydantic ``BaseModel`` instance.

    The message is serialised to JSON with ``preserving_proto_field_name=True``
    so field names round-trip unchanged into ``model_validate_json``.

    Args:
        message: The protobuf message.
        model_type: The target ``BaseModel`` subclass.

    Returns:
        An instance of ``model_type`` populated from ``message``.
    """
    payload = json_format.MessageToJson(
        message,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )
    return model_type.model_validate_json(payload)


def serializer_for(
    registry: DescriptorRegistry, full_name: str
) -> Callable[[BaseModel], bytes]:
    """Return a ``BaseModel`` → wire-bytes serialiser for a registered type.

    Args:
        registry: Registry holding the compiled descriptor for *full_name*.
        full_name: Fully-qualified protobuf message name.

    Returns:
        A callable encoding a ``BaseModel`` into protobuf wire bytes.
    """
    message_class = registry.get_message_class(full_name)

    def _serialize(model: BaseModel) -> bytes:
        return basemodel_to_protobuf(model, message_class).SerializeToString()

    return _serialize


def deserializer_for[BaseModelT: BaseModel](
    registry: DescriptorRegistry,
    full_name: str,
    model_type: type[BaseModelT],
) -> Callable[[bytes], BaseModelT]:
    """Return a wire-bytes → ``BaseModel`` deserialiser for a registered type.

    Args:
        registry: Registry holding the compiled descriptor for *full_name*.
        full_name: Fully-qualified protobuf message name.
        model_type: The ``BaseModel`` subclass to decode into.

    Returns:
        A callable decoding protobuf wire bytes into *model_type*.
    """
    message_class = registry.get_message_class(full_name)

    def _deserialize(data: bytes) -> BaseModelT:
        message = message_class()
        message.ParseFromString(data)
        return protobuf_to_basemodel(message, model_type)

    return _deserialize
