"""Copy a JSON Schema 2020-12 schema into the form one provider accepts.

Providers accept only part of JSON Schema for grammar-constrained output.
These functions build the wire copy that a provider accepts. A wire copy
either keeps the schema's meaning, or accepts more values than the schema
(for example, it leaves out ``minLength``). It never accepts fewer values,
except where the provider itself requires closed objects. The framework
validates the model output against the full schema with
:class:`spakky.plugins.llm.codec.LlmJsonCodec`, so the removed keywords
still hold.

When a provider cannot represent a schema even in a wider form, the strict
functions return ``None``. The provider adapter then uses a looser request.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from json import dumps
from typing import cast

from spakky.agent import JsonObject, JsonValue

from spakky.plugins.llm.codec import schema_type_names
from spakky.plugins.llm.error import LlmUnsupportedFeatureError

_SINGLE_SUBSCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
"""2020-12 keywords whose value is one subschema."""
_SUBSCHEMA_LIST_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
"""2020-12 keywords whose value is an array of subschemas."""
_SUBSCHEMA_MAP_KEYWORDS = frozenset(
    {"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"}
)
"""2020-12 keywords whose value maps names to subschemas."""
_ANNOTATION_KEYWORDS = frozenset(
    {
        "$comment",
        "default",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    }
)
"""Keywords that describe a schema and never change which values it accepts."""
_ROOT_ONLY_KEYWORDS = frozenset({"$defs", "$id", "$schema", "definitions"})
"""Keywords that must stay on the schema that holds them."""
_EVALUATION_KEYWORDS = frozenset(
    {
        "$dynamicRef",
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "contains",
        "dependentSchemas",
        "else",
        "if",
        "items",
        "oneOf",
        "patternProperties",
        "prefixItems",
        "properties",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
"""Keywords whose results ``unevaluatedProperties`` and ``unevaluatedItems`` read."""
_IN_PLACE_KEYWORDS = frozenset(
    {
        "$dynamicRef",
        "$ref",
        "allOf",
        "anyOf",
        "dependentSchemas",
        "else",
        "if",
        "oneOf",
        "then",
    }
)
"""Keywords that apply other subschemas to the same instance."""
_PROPERTY_KEYWORDS = frozenset({"patternProperties", "properties"})
"""Keywords that admit named properties."""
_LOCAL_DEFINITION_PREFIX = "#/$defs/"
"""Reference prefix of a local ``$defs`` entry."""
_ROOT_REFERENCE = "#"
"""Reference to the root schema."""
_STRUCTURED_OUTPUT_INSTRUCTION = (
    "Respond with only one JSON value and no other text. "
    "The JSON value must be valid against this JSON Schema (draft 2020-12):\n"
)
"""Instruction that asks for JSON when a provider cannot constrain the output."""


class _UnrepresentableSchemaError(LlmUnsupportedFeatureError):
    """A provider cannot accept the schema, even in a wider form."""


@dataclass(frozen=True, slots=True)
class _Dialect:
    """The schema rules one provider documents for constrained output."""

    drop: frozenset[str]
    """Keywords to leave out. Leaving them out only widens the schema."""
    keep: frozenset[str] | None
    """Keywords to keep, or ``None`` to keep every keyword not named elsewhere."""
    reject: frozenset[str]
    """Keywords the provider cannot accept in any wider form."""
    close_objects: bool
    """The provider requires ``additionalProperties: false`` on every object."""
    require_all_properties: bool
    """The provider requires every property in ``required``."""
    scalar_enums_only: bool
    """The provider accepts ``enum`` and ``const`` only with scalar values."""
    max_min_items: int | None
    """The largest ``minItems`` the provider accepts, or ``None`` for any."""
    const_as_enum: bool
    """Write ``const`` as a one-value ``enum``."""
    any_of_with_siblings: bool
    """The provider accepts ``anyOf`` next to ``type`` or ``properties``."""
    allow_recursion: bool
    """The provider accepts recursive ``$ref``."""
    root_object_only: bool
    """The provider requires an object root without ``anyOf``."""
    drop_foreign_references: bool
    """Leave out a ``$ref`` outside ``#`` and ``#/$defs/``, instead of failing."""


_OPENAI_STRICT = _Dialect(
    drop=frozenset({"dependentRequired", "not"}),
    keep=None,
    reject=frozenset({"allOf", "dependentSchemas", "else", "if", "then"}),
    close_objects=True,
    require_all_properties=True,
    scalar_enums_only=False,
    max_min_items=None,
    const_as_enum=False,
    any_of_with_siblings=True,
    allow_recursion=True,
    root_object_only=True,
    drop_foreign_references=False,
)
"""OpenAI Structured Outputs, "Supported schemas" (checked 2026-11-25).

https://developers.openai.com/api/docs/guides/structured-outputs lists
``allOf``, ``not``, ``dependentRequired``, ``dependentSchemas``, ``if``,
``then`` and ``else`` as not supported. It requires an object root without
``anyOf``, every property in ``required`` and ``additionalProperties: false``.
"""

_ANTHROPIC_STRICT = _Dialect(
    drop=frozenset(
        {
            "contains",
            "exclusiveMaximum",
            "exclusiveMinimum",
            "maxContains",
            "maxItems",
            "maxLength",
            "maximum",
            "minContains",
            "minLength",
            "minimum",
            "multipleOf",
            "not",
            "uniqueItems",
        }
    ),
    keep=None,
    reject=frozenset({"allOf", "dependentSchemas", "else", "if", "then"}),
    close_objects=True,
    require_all_properties=False,
    scalar_enums_only=True,
    max_min_items=1,
    const_as_enum=False,
    any_of_with_siblings=False,
    allow_recursion=False,
    root_object_only=False,
    drop_foreign_references=False,
)
"""Claude structured outputs, "JSON Schema limitations" (checked 2026-11-25).

https://platform.claude.com/docs/en/build-with-claude/structured-outputs lists
as not supported: recursive schemas, ``oneOf``, ``not``, ``anyOf`` next to
``type`` or ``properties``, complex enums, external ``$ref``, numeric and
string length constraints, array constraints other than ``minItems`` 0 or 1,
and ``additionalProperties`` other than ``false``.
"""

_GEMINI = _Dialect(
    drop=frozenset(),
    keep=frozenset(
        {
            "$defs",
            "$ref",
            "additionalProperties",
            "anyOf",
            "contains",
            "description",
            "enum",
            "format",
            "items",
            "maxContains",
            "maxItems",
            "maxLength",
            "maxProperties",
            "maximum",
            "minContains",
            "minItems",
            "minLength",
            "minProperties",
            "minimum",
            "prefixItems",
            "properties",
            "required",
            "title",
            "type",
            "uniqueItems",
        }
    ),
    reject=frozenset(),
    close_objects=False,
    require_all_properties=False,
    scalar_enums_only=False,
    max_min_items=None,
    const_as_enum=True,
    any_of_with_siblings=True,
    allow_recursion=True,
    root_object_only=False,
    drop_foreign_references=True,
)
"""Gemini structured output, supported JSON Schema (checked 2026-11-25).

https://ai.google.dev/gemini-api/docs/structured-output lists the supported
``type`` values and keywords. Its examples also use ``anyOf``, ``$ref`` and
``$defs``. Every other keyword is left out, which only widens the schema.
"""


def openai_strict_schema(schema: Mapping[str, JsonValue]) -> JsonObject | None:
    """Return the OpenAI strict wire schema, or ``None`` if strict cannot hold it."""
    return _strict_schema(schema, _OPENAI_STRICT)


def anthropic_strict_schema(schema: Mapping[str, JsonValue]) -> JsonObject | None:
    """Return the Claude strict wire schema, or ``None`` if strict cannot hold it."""
    return _strict_schema(schema, _ANTHROPIC_STRICT)


def gemini_schema(schema: Mapping[str, JsonValue]) -> JsonObject:
    """Return the Gemini wire schema. Gemini accepts every result of widening."""
    return _project_object(schema, _GEMINI)


def structured_output_instruction(schema: Mapping[str, JsonValue]) -> str:
    """Return the instruction that asks for JSON valid against ``schema``."""
    return _STRUCTURED_OUTPUT_INSTRUCTION + dumps(
        schema, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _strict_schema(
    schema: Mapping[str, JsonValue],
    dialect: _Dialect,
) -> JsonObject | None:
    try:
        if not dialect.allow_recursion and _is_recursive(schema):
            raise _UnrepresentableSchemaError
        wire = _project_object(schema, dialect)
        if dialect.root_object_only and (
            schema_type_names(wire) != ("object",) or "anyOf" in wire
        ):
            raise _UnrepresentableSchemaError
    except _UnrepresentableSchemaError:
        return None
    return wire


def _project(value: JsonValue, dialect: _Dialect) -> JsonValue:
    if value is True or value is False:
        return value
    if not isinstance(value, Mapping):
        raise _UnrepresentableSchemaError
    return _project_object(value, dialect)


def _project_object(schema: Mapping[str, JsonValue], dialect: _Dialect) -> JsonObject:
    result: dict[str, JsonValue] = {}
    taken: set[str] = set()
    for key, value in schema.items():
        if key in dialect.reject:
            raise _UnrepresentableSchemaError
        wire_key = "anyOf" if key == "oneOf" else key
        if (
            key in dialect.drop
            or wire_key in result
            or (
                dialect.keep is not None
                and wire_key not in dialect.keep
                and not (key == "const" and dialect.const_as_enum)
            )
        ):
            continue
        if key == "$ref":
            if not _is_local_reference(value):
                if dialect.drop_foreign_references:
                    continue
                raise _UnrepresentableSchemaError
            result[key] = value
        elif key in _SINGLE_SUBSCHEMA_KEYWORDS:
            result[wire_key] = _project(value, dialect)
        elif key in _SUBSCHEMA_LIST_KEYWORDS:
            result[wire_key] = _project_list(value, dialect)
        elif key in _SUBSCHEMA_MAP_KEYWORDS:
            result[wire_key] = _project_map(value, dialect)
        elif key == "const" and dialect.const_as_enum:
            result["enum"] = (value,)
        else:
            result[key] = value
        taken.add(key)
    if dialect.scalar_enums_only:
        for key in ("enum", "const"):
            if key in result and not _scalar_data(result[key], key):
                del result[key]
    _keep_dependent_keywords_wide(result, frozenset(schema) - taken)
    min_items = result.get("minItems")
    if (
        dialect.max_min_items is not None
        and isinstance(min_items, int)
        and min_items > dialect.max_min_items
    ):
        result["minItems"] = dialect.max_min_items
    if dialect.close_objects:
        _reject_closed_conjunctions(result)
    if "object" in schema_type_names(result):
        _close_object(result, dialect)
    if not dialect.any_of_with_siblings and "anyOf" in result:
        return _distribute_any_of(result, dialect)
    return result


def _keep_dependent_keywords_wide(
    result: dict[str, JsonValue],
    dropped: frozenset[str],
) -> None:
    """Leave out keywords whose meaning depends on a keyword already left out.

    ``additionalProperties`` reads ``patternProperties``, and
    ``unevaluated*`` read every applicator next to them. Keeping one of them
    after its input is gone would reject values the full schema accepts.
    Only Gemini leaves out ``patternProperties``, and Gemini does not close
    objects, so ``additionalProperties`` can leave too.
    """
    if "patternProperties" in dropped:
        result.pop("additionalProperties", None)
    if dropped & _EVALUATION_KEYWORDS or result.keys() & _IN_PLACE_KEYWORDS:
        result.pop("unevaluatedItems", None)
        result.pop("unevaluatedProperties", None)


def _reject_closed_conjunctions(result: Mapping[str, JsonValue]) -> None:
    """Fail when closing objects would forbid what the full schema accepts.

    A ``$ref`` target and an object branch under ``anyOf`` are closed on
    their own. When they meet an object schema that lists properties, each
    closed part forbids the other's properties.
    """
    if not (
        "object" in schema_type_names(result) or result.keys() & _PROPERTY_KEYWORDS
    ):
        return
    if "$ref" in result:
        raise _UnrepresentableSchemaError
    # cast: _project_list has already turned "anyOf" into a tuple of schemas.
    for branch in cast(tuple[JsonValue, ...], result.get("anyOf", ())):
        if isinstance(branch, Mapping) and (
            "object" in schema_type_names(branch)
            or branch.keys() & (_PROPERTY_KEYWORDS | {"$ref"})
        ):
            raise _UnrepresentableSchemaError


def _project_list(value: JsonValue, dialect: _Dialect) -> tuple[JsonValue, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise _UnrepresentableSchemaError
    return tuple(_project(item, dialect) for item in value)


def _project_map(value: JsonValue, dialect: _Dialect) -> JsonObject:
    if not isinstance(value, Mapping):
        raise _UnrepresentableSchemaError
    return {name: _project(item, dialect) for name, item in value.items()}


def _close_object(result: dict[str, JsonValue], dialect: _Dialect) -> None:
    if not dialect.close_objects:
        return
    if isinstance(result.get("additionalProperties"), Mapping):
        raise _UnrepresentableSchemaError
    result["additionalProperties"] = False
    if dialect.require_all_properties:
        # cast: _project_map has already turned "properties" into a JsonObject.
        properties = cast(JsonObject, result.get("properties", {}))
        result["required"] = tuple(properties)


def _distribute_any_of(result: dict[str, JsonValue], dialect: _Dialect) -> JsonObject:
    """Move assertions next to ``anyOf`` into every branch.

    ``A and (B or C)`` equals ``(A and B) or (A and C)``, so the schema keeps
    its meaning. A branch that repeats a sibling keyword cannot be merged.
    """
    siblings = {
        key: value
        for key, value in result.items()
        if key != "anyOf"
        and key not in _ANNOTATION_KEYWORDS
        and key not in _ROOT_ONLY_KEYWORDS
    }
    if not siblings:
        return result
    branches: list[JsonValue] = []
    for branch in _project_list(result["anyOf"], dialect):
        if not isinstance(branch, Mapping) or siblings.keys() & branch.keys():
            raise _UnrepresentableSchemaError
        branches.append(_project_object({**siblings, **branch}, dialect))
    kept = {
        key: value
        for key, value in result.items()
        if key in _ANNOTATION_KEYWORDS or key in _ROOT_ONLY_KEYWORDS
    }
    return {**kept, "anyOf": tuple(branches)}


def _scalar_data(value: JsonValue, key: str) -> bool:
    values = value if key == "enum" and isinstance(value, Sequence) else (value,)
    return all(
        not isinstance(item, Mapping | Sequence) or isinstance(item, str)
        for item in values
    )


def _is_local_reference(value: JsonValue) -> bool:
    """Accept ``#`` and ``#/$defs/<name>``; deeper pointers are not accepted."""
    if not isinstance(value, str):
        return False
    if value == _ROOT_REFERENCE:
        return True
    name = value.removeprefix(_LOCAL_DEFINITION_PREFIX)
    return name != value and name != "" and "/" not in name


def _is_recursive(schema: Mapping[str, JsonValue]) -> bool:
    """Return whether a ``$ref`` can reach the schema that holds it."""
    references = _references(schema)
    if _ROOT_REFERENCE in references:
        return True
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, Mapping):
        return False
    graph = {
        name: {
            ref.removeprefix(_LOCAL_DEFINITION_PREFIX)
            for ref in _references(target)
            if ref.startswith(_LOCAL_DEFINITION_PREFIX)
        }
        for name, target in definitions.items()
    }
    return any(_reaches(name, name, graph, set()) for name in graph)


def _reaches(
    start: str,
    current: str,
    graph: Mapping[str, set[str]],
    seen: set[str],
) -> bool:
    for name in graph.get(current, set()):
        if name == start:
            return True
        if name not in seen:
            seen.add(name)
            if _reaches(start, name, graph, seen):
                return True
    return False


def _references(value: JsonValue) -> set[str]:
    """Collect every ``$ref`` string in a schema, reading subschemas only."""
    found: set[str] = set()
    if not isinstance(value, Mapping):
        return found
    for key, item in value.items():
        if key == "$ref" and isinstance(item, str):
            found.add(item)
        elif key in _SINGLE_SUBSCHEMA_KEYWORDS:
            found |= _references(item)
        elif key in _SUBSCHEMA_LIST_KEYWORDS and isinstance(item, Sequence):
            for subschema in item:
                found |= _references(subschema)
        elif key in _SUBSCHEMA_MAP_KEYWORDS and isinstance(item, Mapping):
            for subschema in item.values():
                found |= _references(subschema)
    return found
