"""Helpers that build gRPC callables against the code-first descriptor pool.

All helpers route through the ``google.protobuf.json_format`` bridge so
that client-side serialisation mirrors the server-side pydantic
``BaseModel`` ↔ protobuf translation. This keeps integration tests free
of dynamic protobuf attribute access.
"""

from collections.abc import Callable
from typing import TypeVar

from google.protobuf import json_format
from pydantic import BaseModel

from spakky.plugins.grpc.schema.registry import DescriptorRegistry

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


def serializer_for(
    registry: DescriptorRegistry, full_name: str
) -> Callable[[BaseModel], bytes]:
    """Return a ``BaseModel → bytes`` serialiser for the registered type.

    The returned callable converts the ``BaseModel`` to a protobuf
    ``Message`` via ``json_format.Parse`` (using the registered message
    class) and then serialises it to the wire format.
    """
    message_class = registry.get_message_class(full_name)

    def _serialize(model: BaseModel) -> bytes:
        msg = json_format.Parse(model.model_dump_json(), message_class())
        return msg.SerializeToString()

    return _serialize


def deserializer_for(
    registry: DescriptorRegistry,
    full_name: str,
    model_type: type[BaseModelT],
) -> Callable[[bytes], BaseModelT]:
    """Return a ``bytes → BaseModel`` deserialiser for the registered type."""
    message_class = registry.get_message_class(full_name)

    def _deserialize(data: bytes) -> BaseModelT:
        instance = message_class()
        instance.ParseFromString(data)
        payload = json_format.MessageToJson(
            instance,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        )
        return model_type.model_validate_json(payload)

    return _deserialize
