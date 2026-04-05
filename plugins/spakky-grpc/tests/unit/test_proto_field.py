"""Unit tests for ProtoField annotation."""

from dataclasses import dataclass
from typing import Annotated, get_type_hints

import pytest
from spakky.plugins.grpc.annotations.field import ProtoField


def test_proto_field_stores_number() -> None:
    """ProtoField should store the field number."""
    field = ProtoField(number=1)
    assert field.number == 1


def test_proto_field_is_frozen() -> None:
    """ProtoField should be immutable."""
    field = ProtoField(number=1)
    with pytest.raises(AttributeError):
        field.number = 2  # type: ignore[misc]


def test_proto_field_equality() -> None:
    """ProtoField instances with the same number should be equal."""
    assert ProtoField(number=1) == ProtoField(number=1)
    assert ProtoField(number=1) != ProtoField(number=2)


def test_proto_field_in_annotated_type() -> None:
    """ProtoField should be extractable from Annotated type hints."""

    @dataclass
    class HelloRequest:
        name: Annotated[str, ProtoField(number=1)]
        greeting_count: Annotated[int, ProtoField(number=2)]

    hints = get_type_hints(HelloRequest, include_extras=True)
    name_metadata = hints["name"].__metadata__
    count_metadata = hints["greeting_count"].__metadata__

    assert name_metadata[0] == ProtoField(number=1)
    assert count_metadata[0] == ProtoField(number=2)


def test_proto_field_hash() -> None:
    """ProtoField should be hashable for use in sets and dicts."""
    fields = {ProtoField(number=1), ProtoField(number=2), ProtoField(number=1)}
    assert len(fields) == 2
