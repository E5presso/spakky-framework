"""Unit tests for ProtoField annotation."""

from typing import Annotated

import pytest
from pydantic import BaseModel
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


def test_proto_field_in_basemodel_metadata() -> None:
    """ProtoField should be readable from pydantic model_fields[name].metadata."""

    class HelloRequest(BaseModel):
        name: Annotated[str, ProtoField(number=1)]
        greeting_count: Annotated[int, ProtoField(number=2)]

    name_metadata = HelloRequest.model_fields["name"].metadata
    count_metadata = HelloRequest.model_fields["greeting_count"].metadata

    assert ProtoField(number=1) in name_metadata
    assert ProtoField(number=2) in count_metadata


def test_proto_field_hash() -> None:
    """ProtoField should be hashable for use in sets and dicts."""
    fields = {ProtoField(number=1), ProtoField(number=2), ProtoField(number=1)}
    assert len(fields) == 2
