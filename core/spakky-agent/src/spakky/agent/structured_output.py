"""Typed structured-output contracts owned by the agent declaration."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, is_dataclass
from functools import cache
from json import dumps
from math import isfinite
from typing import is_typeddict

from pydantic import (
    BaseModel,
    PydanticUserError,
    TypeAdapter,
    ValidationError,
)
from pydantic_core import PydanticSerializationError

from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import JsonSchemaConstraint, StructuredOutputSpec
from spakky.agent.types import JsonObject, JsonValue

_LOCAL_REF_PREFIX = "#/$defs/"
_DEFINITIONS_KEYWORD = "$defs"
"""Keyword that holds the definitions a recursive output schema refers to."""
_REFERENCE_KEYWORD = "$ref"
"""Keyword of a JSON Schema reference."""
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
_DATA_KEYWORDS = frozenset({"const", "default", "enum", "examples"})
"""Keywords whose values are instance data, not subschemas."""
_NAME_MAP_KEYWORDS = frozenset({"dependentSchemas", "patternProperties", "properties"})
"""Keywords whose values map user-chosen names to subschemas."""


@dataclass(frozen=True, slots=True)
class _StructuredOutputContract:
    """Validated TypeAdapter, portable schema, and exact materialization boundary."""

    output_type: type[object]
    adapter: TypeAdapter[object]
    spec: StructuredOutputSpec

    def materialize(self, value: JsonValue) -> object:
        """Strictly materialize provider JSON without text fallback or key loss."""
        try:
            encoded = dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            result = self.adapter.validate_json(
                encoded,
                strict=True,
                extra="forbid",
                by_alias=True,
            )
            dumped = self.adapter.dump_python(
                result,
                mode="json",
                by_alias=True,
                exclude_computed_fields=True,
                warnings="error",
            )
        except (
            PydanticSerializationError,
            ValidationError,
            TypeError,
            ValueError,
        ) as error:
            raise AgentDefinitionError(
                "Agent structured output does not satisfy its declared type"
            ) from error
        normalized = _json_value(dumped)
        if not _same_json_shape(value, normalized):
            raise AgentDefinitionError(
                "Agent structured output materialization changed its JSON shape"
            )
        return result

    def dump(self, value: object) -> JsonValue:
        """Return the JSON-safe representation used by protocol final events."""
        try:
            dumped = self.adapter.dump_python(
                value,
                mode="json",
                by_alias=True,
                exclude_computed_fields=True,
                warnings="error",
            )
        except (PydanticSerializationError, TypeError, ValueError) as error:
            raise AgentDefinitionError(
                "Agent structured output could not be serialized"
            ) from error
        return _json_value(dumped)


@cache
def _structured_output_contract(
    output_type: type[object],
) -> _StructuredOutputContract:
    """Build the declaration-time contract for one supported output class."""
    if not _supported_output_type(output_type):
        raise AgentDefinitionError(
            "Agent output type must be a BaseModel, dataclass, or TypedDict"
        )
    try:
        adapter: TypeAdapter[object] = TypeAdapter(output_type)
        raw_schema: object = adapter.json_schema(by_alias=True, mode="validation")
    except PydanticUserError as error:
        raise AgentDefinitionError(
            "Agent output type cannot produce a JSON schema"
        ) from error
    schema = _portable_schema(raw_schema)
    return _StructuredOutputContract(
        output_type=output_type,
        adapter=adapter,
        spec=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(schema=schema, strict=True),
            output_type_name=output_type.__name__,
        ),
    )


def _supported_output_type(output_type: type[object]) -> bool:
    return (
        issubclass(output_type, BaseModel)
        or is_dataclass(output_type)
        or is_typeddict(output_type)
    )


def _portable_schema(raw_schema: object) -> JsonObject:
    """Copy a Pydantic JSON Schema into a self-contained 2020-12 schema.

    Local ``#/$defs/...`` references are inlined. A reference that would
    recurse stays a ``$ref``, and the root keeps only the definitions such
    references need. Every other JSON Schema keyword is kept as written.
    """
    if not isinstance(raw_schema, Mapping):
        raise AgentDefinitionError("Agent structured output schema must be an object")
    raw_defs = raw_schema.get(_DEFINITIONS_KEYWORD, {})
    if not isinstance(raw_defs, Mapping):
        raise AgentDefinitionError("Agent structured output definitions are invalid")
    defs = {str(key): value for key, value in raw_defs.items()}
    root = {
        key: value for key, value in raw_schema.items() if key != _DEFINITIONS_KEYWORD
    }
    recursive: dict[str, JsonValue] = {}
    normalized = (
        _normalize_reference(root, defs, (), recursive)
        if _REFERENCE_KEYWORD in root
        else _normalize_schema_object(root, defs, (), recursive)
    )
    pending = [name for name in recursive if recursive[name] is None]
    while pending:
        for name in pending:
            recursive[name] = _normalize_schema_node(
                defs[name], defs, (name,), recursive
            )
        pending = [name for name in recursive if recursive[name] is None]
    if not recursive:
        return normalized
    return {**normalized, _DEFINITIONS_KEYWORD: recursive}


def _normalize_schema_node(
    value: object,
    defs: Mapping[str, object],
    resolving: tuple[str, ...],
    recursive: dict[str, JsonValue],
) -> JsonValue:
    if not isinstance(value, Mapping):
        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            return tuple(
                _normalize_schema_node(item, defs, resolving, recursive)
                for item in value
            )
        return _json_value(value)
    if _REFERENCE_KEYWORD in value:
        return _normalize_reference(value, defs, resolving, recursive)
    return _normalize_schema_object(value, defs, resolving, recursive)


def _normalize_schema_object(
    value: Mapping[object, object],
    defs: Mapping[str, object],
    resolving: tuple[str, ...],
    recursive: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    normalized: dict[str, JsonValue] = {}
    for raw_key, item in value.items():
        if not isinstance(raw_key, str):
            raise AgentDefinitionError("Agent structured output key is not text")
        if raw_key in _DATA_KEYWORDS:
            normalized[raw_key] = _json_value(item)
        elif raw_key in _NAME_MAP_KEYWORDS:
            if not isinstance(item, Mapping):
                raise AgentDefinitionError(
                    "Agent structured output properties are invalid"
                )
            normalized[raw_key] = {
                str(name): _normalize_schema_node(schema, defs, resolving, recursive)
                for name, schema in item.items()
            }
        else:
            normalized[raw_key] = _normalize_schema_node(
                item, defs, resolving, recursive
            )
    if normalized.get("type") == "object":
        properties = normalized.get("properties")
        if isinstance(properties, Mapping) or "additionalProperties" not in normalized:
            normalized["additionalProperties"] = False
    return normalized


def _normalize_reference(
    value: Mapping[object, object],
    defs: Mapping[str, object],
    resolving: tuple[str, ...],
    recursive: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Inline a local reference, or keep it when it would recurse.

    Annotation siblings such as ``description`` are copied onto the inlined
    schema. Other siblings keep their 2020-12 meaning through ``allOf``.
    """
    ref = value[_REFERENCE_KEYWORD]
    if not isinstance(ref, str) or not ref.startswith(_LOCAL_REF_PREFIX):
        raise AgentDefinitionError("Agent structured output reference is unsupported")
    name = ref.removeprefix(_LOCAL_REF_PREFIX)
    if name not in defs:
        raise AgentDefinitionError("Agent structured output reference is missing")
    normalized_siblings = _normalize_schema_object(
        {key: item for key, item in value.items() if key != _REFERENCE_KEYWORD},
        defs,
        resolving,
        recursive,
    )
    if name in resolving:
        recursive.setdefault(name, None)
        target: JsonValue = {_REFERENCE_KEYWORD: ref}
    else:
        target = _normalize_schema_node(defs[name], defs, (*resolving, name), recursive)
    if not isinstance(target, Mapping):
        raise AgentDefinitionError("Agent structured output schema must be an object")
    annotations = {
        key: item
        for key, item in normalized_siblings.items()
        if key in _ANNOTATION_KEYWORDS
    }
    assertions = {
        key: item
        for key, item in normalized_siblings.items()
        if key not in _ANNOTATION_KEYWORDS
    }
    if assertions:
        sibling_all_of = assertions.get("allOf", ())
        if not isinstance(sibling_all_of, Sequence) or isinstance(sibling_all_of, str):
            raise AgentDefinitionError("Agent structured output allOf is invalid")
        return {**annotations, **assertions, "allOf": (target, *sibling_all_of)}
    return {**target, **annotations}


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise AgentDefinitionError("Agent structured output is not finite JSON")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentDefinitionError("Agent structured output key is not text")
            result[key] = _json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_json_value(item) for item in value)
    raise AgentDefinitionError("Agent structured output is not JSON serializable")


def _same_json_shape(left: JsonValue, right: JsonValue) -> bool:
    if isinstance(left, Mapping):
        return (
            isinstance(right, Mapping)
            and left.keys() <= right.keys()
            and all(_same_json_shape(value, right[key]) for key, value in left.items())
        )
    if isinstance(left, Sequence) and not isinstance(left, str):
        return (
            isinstance(right, Sequence)
            and not isinstance(right, str)
            and len(left) == len(right)
            and all(
                _same_json_shape(left_item, right_item)
                for left_item, right_item in zip(left, right, strict=True)
            )
        )
    return type(left) is type(right)
