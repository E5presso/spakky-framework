"""Deterministic protobuf field-number assignment from field names.

Assigns protobuf field numbers to pydantic ``BaseModel`` fields without
requiring an explicit :class:`ProtoField` annotation. Each number is
derived from a stable hash of the field *name*. Explicit ``ProtoField``
annotations override the derived number for the annotated field.

Protobuf field-number constraints honored here:

- Valid range is ``1`` .. ``536_870_911`` (``2**29 - 1``).
- The range ``19_000`` .. ``19_999`` is reserved by protobuf and is never
  assigned.

The auto path satisfies these constraints by construction. An explicit
``ProtoField`` override bypasses that construction, so the same invariants
are enforced on it up front — an out-of-range or reserved number, or two
explicit fields sharing a number, fails at schema-build time with a custom
error instead of an opaque descriptor-pool rejection later.

Collisions within a single message (two field names hashing to the same
number, or a derived number landing on an explicit override) are resolved
by deterministic re-hashing of the colliding name with an incrementing
salt. Re-hashing operates on names sorted lexicographically, so the final
assignment is a pure function of the *set* of field names plus their
explicit overrides — independent of declaration order.

Wire-compatibility guarantee and its single boundary:

- **Reordering** a message's fields never changes any number — the
  assignment depends only on the set of names, not their declaration
  order. This is absolute.
- **Adding** a field never changes the numbers of pre-existing fields,
  *except* when the new name's primary (salt-0) number equals a slot a
  pre-existing field already occupies. Because derived names are processed
  in sorted order, a newly added name that sorts ahead of an existing name
  and shares its salt-0 number takes that slot and forces the existing
  field to re-hash. This is the only case where an existing number can
  change, and it requires a SHA-256 salt-0 collision in the
  ~536-million-wide assignable space (probability ~1 in 5.4e8 per name
  pair). The outcome stays fully deterministic and reproducible from the
  field names alone; it is never silently nondeterministic. Callers that
  need an unconditional number lock for a specific field pin it with an
  explicit ``ProtoField(number=N)``.
"""

from hashlib import sha256

from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.error import (
    DuplicateProtoFieldNumberError,
    InvalidProtoFieldNumberError,
    ProtoFieldNumberConflictError,
)

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


def _validate_explicit_number(
    model_type: type[BaseModel], field_name: str, number: int
) -> None:
    """Enforce protobuf number invariants on an explicit ProtoField override.

    The auto-numbering path produces only valid, non-reserved numbers by
    construction (:func:`_hash_to_number`). An explicit override skips that
    construction, so the same invariants are checked here: the number must lie
    in ``MIN_FIELD_NUMBER`` .. ``MAX_FIELD_NUMBER`` and must not fall in the
    reserved ``RESERVED_RANGE_START`` .. ``RESERVED_RANGE_END`` band.

    Args:
        model_type: The ``BaseModel`` subclass being numbered (error context).
        field_name: The field carrying the explicit override (error context).
        number: The explicit protobuf field number to validate.

    Raises:
        InvalidProtoFieldNumberError: If the number is out of the valid range
            or lands in the reserved band.
    """
    if not MIN_FIELD_NUMBER <= number <= MAX_FIELD_NUMBER:
        raise InvalidProtoFieldNumberError(model_type, field_name, number)
    if RESERVED_RANGE_START <= number <= RESERVED_RANGE_END:
        raise InvalidProtoFieldNumberError(model_type, field_name, number)


def assign_field_numbers(model_type: type[BaseModel]) -> dict[str, int]:
    """Assign a protobuf field number to every field of a ``BaseModel``.

    Fields carrying an explicit :class:`ProtoField` annotation are assigned
    that exact number after the same protobuf invariants the auto path honors
    are enforced on it: the number must be in the valid range and outside the
    reserved band, and no two explicit fields may share a number. All remaining
    fields receive a number derived from a stable hash of their name, processed
    in lexicographic order. Collisions between two derived numbers are resolved
    by deterministic re-hashing.

    A derived field's primary (salt-0) number colliding with an explicit
    override is *not* silently re-hashed — that would change the auto field's
    wire number whenever an explicit field claims it. Such a collision raises
    :class:`ProtoFieldNumberConflictError` so the author resolves it
    explicitly (pin the auto field too, or pick a different number).

    Args:
        model_type: The ``BaseModel`` subclass whose fields to number.

    Returns:
        A mapping of field name to assigned protobuf field number.

    Raises:
        InvalidProtoFieldNumberError: If an explicit ``ProtoField`` number is
            outside the valid range or lands in the reserved band.
        DuplicateProtoFieldNumberError: If two explicit ``ProtoField`` numbers
            are equal within the same message.
        ProtoFieldNumberConflictError: If an auto-derived field's primary
            number equals an explicit ``ProtoField`` number in the same
            message.
    """
    assigned: dict[str, int] = {}
    used: set[int] = set()
    explicit_owner: dict[int, str] = {}
    derived_names: list[str] = []

    for field_name, field_info in model_type.model_fields.items():
        override = next(
            (meta for meta in field_info.metadata if isinstance(meta, ProtoField)),
            None,
        )
        if override is not None:
            _validate_explicit_number(model_type, field_name, override.number)
            if override.number in explicit_owner:
                raise DuplicateProtoFieldNumberError(
                    model_type,
                    explicit_owner[override.number],
                    field_name,
                    override.number,
                )
            assigned[field_name] = override.number
            used.add(override.number)
            explicit_owner[override.number] = field_name
        else:
            derived_names.append(field_name)

    for field_name in sorted(derived_names):
        primary = _hash_to_number(field_name, 0)
        if primary in explicit_owner:
            raise ProtoFieldNumberConflictError(
                model_type, explicit_owner[primary], field_name, primary
            )
        salt = 0
        number = primary
        while number in used:
            salt += 1
            number = _hash_to_number(field_name, salt)
        assigned[field_name] = number
        used.add(number)

    return assigned
