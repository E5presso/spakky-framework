"""Deterministic protobuf field-number assignment from field names.

Assigns protobuf field numbers to pydantic ``BaseModel`` fields without
requiring an explicit :class:`ProtoField` annotation. Each number is
derived from a stable hash of the field *name*, so adding or reordering
fields never changes the numbers of pre-existing fields (wire
compatibility). Explicit ``ProtoField`` annotations override the derived
number for the annotated field.

Protobuf field-number constraints honored here:

- Valid range is ``1`` .. ``536_870_911`` (``2**29 - 1``).
- The range ``19_000`` .. ``19_999`` is reserved by protobuf and is never
  assigned.

Collisions within a single message (two field names hashing to the same
number, or a derived number landing on an explicit override) are resolved
by deterministic re-hashing of the colliding name with an incrementing
salt. Re-hashing operates on names sorted lexicographically, so the final
assignment is a pure function of the *set* of field names plus their
explicit overrides — independent of declaration order.
"""

from hashlib import sha256

from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField

MIN_FIELD_NUMBER = 1
"""Smallest valid protobuf field number."""

MAX_FIELD_NUMBER = 2**29 - 1
"""Largest valid protobuf field number (536,870,911)."""

RESERVED_RANGE_START = 19_000
"""First protobuf field number reserved by the wire format."""

RESERVED_RANGE_END = 19_999
"""Last protobuf field number reserved by the wire format."""

_RESERVED_SPAN = RESERVED_RANGE_END - RESERVED_RANGE_START + 1
"""Count of reserved numbers excluded from the assignable space."""

_ASSIGNABLE_COUNT = MAX_FIELD_NUMBER - _RESERVED_SPAN
"""Count of assignable numbers (valid range minus the reserved span)."""


def _hash_to_number(field_name: str, salt: int) -> int:
    """Map a field name and salt to a valid, non-reserved protobuf number.

    The name and salt are hashed with SHA-256 and folded into the
    assignable number space (``1`` .. ``MAX_FIELD_NUMBER`` excluding the
    reserved ``19_000`` .. ``19_999`` band). The mapping is uniform over
    the assignable space and fully deterministic.

    Args:
        field_name: The pydantic field name.
        salt: A re-hash counter; ``0`` is the primary assignment, higher
            values are used only to resolve collisions.

    Returns:
        A valid protobuf field number that is never in the reserved range.
    """
    digest = sha256(f"{field_name}:{salt}".encode()).digest()
    offset = int.from_bytes(digest, "big") % _ASSIGNABLE_COUNT
    number = MIN_FIELD_NUMBER + offset
    if number >= RESERVED_RANGE_START:
        number += _RESERVED_SPAN
    return number


def assign_field_numbers(model_type: type[BaseModel]) -> dict[str, int]:
    """Assign a protobuf field number to every field of a ``BaseModel``.

    Fields carrying an explicit :class:`ProtoField` annotation are assigned
    that exact number. All remaining fields receive a number derived from a
    stable hash of their name. Collisions (between two derived numbers, or a
    derived number landing on an explicit override) are resolved by
    deterministic re-hashing of the field name sorted lexicographically.

    Args:
        model_type: The ``BaseModel`` subclass whose fields to number.

    Returns:
        A mapping of field name to assigned protobuf field number.
    """
    assigned: dict[str, int] = {}
    used: set[int] = set()
    derived_names: list[str] = []

    for field_name, field_info in model_type.model_fields.items():
        override = next(
            (meta for meta in field_info.metadata if isinstance(meta, ProtoField)),
            None,
        )
        if override is not None:
            assigned[field_name] = override.number
            used.add(override.number)
        else:
            derived_names.append(field_name)

    for field_name in sorted(derived_names):
        salt = 0
        number = _hash_to_number(field_name, salt)
        while number in used:
            salt += 1
            number = _hash_to_number(field_name, salt)
        assigned[field_name] = number
        used.add(number)

    return assigned
