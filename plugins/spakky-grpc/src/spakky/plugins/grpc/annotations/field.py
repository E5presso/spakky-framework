"""Protobuf field annotation for pydantic-based message definitions.

Provides the ProtoField annotation for specifying protobuf field numbers
on pydantic ``BaseModel`` fields using the ``Annotated`` type hint pattern.

Example::

    from pydantic import BaseModel
    from typing import Annotated

    class HelloRequest(BaseModel):
        name: Annotated[str, ProtoField(number=1)]
        greeting_count: Annotated[int, ProtoField(number=2)]
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtoField:
    """Protobuf field number annotation for pydantic model fields.

    Used with ``typing.Annotated`` to specify the protobuf field number
    for a pydantic ``BaseModel`` field, enabling code-first protobuf
    message definition. The annotation is read at runtime from the
    model's ``model_fields[name].metadata`` tuple.

    Attributes:
        number: The protobuf field number. Must be a positive integer.
    """

    number: int
    """The protobuf field number."""
