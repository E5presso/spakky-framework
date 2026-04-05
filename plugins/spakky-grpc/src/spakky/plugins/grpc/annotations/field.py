"""Protobuf field annotation for dataclass-based message definitions.

Provides the ProtoField annotation for specifying protobuf field numbers
on dataclass fields using the Annotated type hint pattern.

Example::

    from dataclasses import dataclass
    from typing import Annotated

    @dataclass
    class HelloRequest:
        name: Annotated[str, ProtoField(number=1)]
        greeting_count: Annotated[int, ProtoField(number=2)]
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtoField:
    """Protobuf field number annotation for dataclass fields.

    Used with ``typing.Annotated`` to specify the protobuf field number
    for a dataclass field, enabling code-first protobuf message definition.

    Attributes:
        number: The protobuf field number. Must be a positive integer.
    """

    number: int
    """The protobuf field number."""
