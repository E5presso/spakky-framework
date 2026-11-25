"""Provider-neutral JSON and tool-call validation helpers."""

from collections.abc import Mapping, Sequence
from json import JSONDecodeError, loads
from math import isfinite
from typing import Never

import jsonschema_rs
from spakky.agent import (
    JsonObject,
    JsonSchemaConstraint,
    JsonValue,
    ToolCallingSpec,
)

from spakky.plugins.llm.error import LlmResponseError

_SCHEMA_KEYWORD_DETAIL = "schema_keyword"
"""Error detail key naming the JSON Schema keyword that was rejected."""
_SCHEMA_REASON_DETAIL = "reason"
"""Error detail key naming why the JSON Schema keyword was rejected."""
_INVALID_SCHEMA_REASON = "invalid_schema"
"""The schema violates the JSON Schema 2020-12 meta-schema."""
_UNRESOLVABLE_REFERENCE_REASON = "unresolvable_reference"
"""A reference points outside the schema and the registered external schemas."""
_VALUE_MISMATCH_REASON = "value_mismatch"
"""The provider value does not satisfy the named keyword."""
_REFERENCE_KEYWORD = "$ref"
"""Keyword reported when a reference cannot be resolved."""
_NAME_MAP_KEYWORDS = frozenset(
    {
        "$defs",
        "$vocabulary",
        "definitions",
        "dependencies",
        "dependentRequired",
        "dependentSchemas",
        "patternProperties",
        "properties",
    }
)
"""Keywords whose object keys are user-chosen names, not schema keywords."""

type PlainJson = (
    None | bool | int | float | str | list[PlainJson] | dict[str, PlainJson]
)
"""JSON with list arrays, the form the validator library reads."""


def schema_type_names(schema: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """Return the type names a schema's ``type`` keyword lists, without validation.

    JSON Schema 2020-12 lets ``type`` be one string or an array of strings.
    Provider wire transforms use this to see whether a schema admits a type
    before :class:`LlmJsonCodec` validates the full shape.

    Args:
        schema: A JSON Schema object.

    Returns:
        The string entries of ``type`` in declaration order, or an empty tuple
        when ``type`` is absent or is neither a string nor an array.
    """
    value = schema.get("type")
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def schema_keyword_at(path: Sequence[str | int]) -> str | None:
    """Return the last JSON Schema keyword in a location path.

    Object keys under ``properties``, ``$defs`` and the other name maps are
    user-chosen names, so they are skipped. Array indexes are skipped too.

    Args:
        path: A location inside a schema, as keys and array indexes.

    Returns:
        The last keyword on the path, or ``None`` when the path names none.
    """
    keyword: str | None = None
    expects_name = False
    for element in path:
        if expects_name:
            expects_name = False
            continue
        if isinstance(element, int):
            continue
        keyword = element
        expects_name = element in _NAME_MAP_KEYWORDS
    return keyword


class LlmJsonCodec:
    """Decode provider JSON and validate it with JSON Schema 2020-12.

    Validation follows the whole 2020-12 dialect. ``format`` is an annotation,
    as the 2020-12 format-annotation vocabulary defines by default. The codec
    never retrieves a remote ``$ref``. A reference outside the schema resolves
    only against the external schemas given to the constructor.
    """

    __registry: jsonschema_rs.Registry | None

    def __init__(
        self,
        external_schemas: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> None:
        """Register schemas that ``$ref`` may name by their retrieval URI.

        Args:
            external_schemas: Schemas keyed by retrieval URI. ``None`` or an
                empty mapping registers nothing.
        """
        if external_schemas is None or len(external_schemas) == 0:
            self.__registry = None
            return
        resources = [
            (uri, _plain_object(self.to_object(schema)))
            for uri, schema in external_schemas.items()
        ]
        try:
            self.__registry = jsonschema_rs.Registry(resources)
        except (
            jsonschema_rs.ReferencingError,
            jsonschema_rs.ValidationError,
            ValueError,
        ) as error:
            raise LlmResponseError(
                details=_reason(_REFERENCE_KEYWORD, _UNRESOLVABLE_REFERENCE_REASON)
            ) from error

    def decode_object(
        self,
        text: str,
        constraint: JsonSchemaConstraint | None = None,
    ) -> JsonObject:
        """Decode and optionally validate a JSON object."""
        if text == "":
            value: JsonObject = {}
        else:
            value = self.to_object(self._loads(text))
        if constraint is not None:
            self.validate(value, constraint.schema)
        return value

    def decode_value(
        self,
        text: str,
        constraint: JsonSchemaConstraint,
    ) -> JsonValue:
        """Decode and validate structured JSON output."""
        if text == "":
            raise LlmResponseError
        value = self.to_value(self._loads(text))
        self.validate(value, constraint.schema)
        return value

    def tool_constraints(
        self,
        tool_calling: ToolCallingSpec | None,
    ) -> Mapping[str, JsonSchemaConstraint] | None:
        """Index declared tool constraints while rejecting duplicate names."""
        if tool_calling is None:
            return None
        constraints: dict[str, JsonSchemaConstraint] = {}
        for tool in tool_calling.tools:
            if tool.name in constraints:
                raise LlmResponseError
            constraints[tool.name] = tool.parameters
        return constraints

    def tool_constraint(
        self,
        name: str,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> JsonSchemaConstraint:
        """Return the declared constraint for a provider-emitted tool name."""
        if constraints is None:
            raise LlmResponseError
        constraint = constraints.get(name)
        if constraint is None:
            raise LlmResponseError
        return constraint

    def to_object(self, value: object) -> JsonObject:
        """Narrow an untyped provider-SDK JSON boundary to a framework object."""
        if not isinstance(value, Mapping):
            raise LlmResponseError
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LlmResponseError
            result[key] = self.to_value(item)
        return result

    def to_value(self, value: object) -> JsonValue:
        """Narrow an untyped provider-SDK JSON boundary to framework JSON."""
        if value is None or isinstance(value, str | int | bool):
            return value
        if isinstance(value, float):
            if not isfinite(value):
                raise LlmResponseError
            return value
        if isinstance(value, Mapping):
            return self.to_object(value)
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            return tuple(self.to_value(item) for item in value)
        raise LlmResponseError

    def check_schema(self, schema: Mapping[str, JsonValue]) -> None:
        """Reject a schema that JSON Schema 2020-12 does not accept.

        Raises:
            LlmResponseError: The schema violates the 2020-12 meta-schema or
                has a reference that cannot be resolved. ``details`` names the
                keyword and the reason, and never copies schema values.
        """
        self._validator(self.to_object(schema))

    def validate(
        self,
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        """Validate a value against a JSON Schema 2020-12 schema.

        Raises:
            LlmResponseError: The schema is rejected, or the value does not
                satisfy it. ``details`` names the keyword and the reason, and
                never copies schema values or the value.
        """
        normalized_value = _plain_json(self.to_value(value))
        validator = self._validator(self.to_object(schema))
        for error in validator.iter_errors(normalized_value):
            raise LlmResponseError(
                details=_reason(
                    schema_keyword_at(list(error.schema_path)),
                    _VALUE_MISMATCH_REASON,
                )
            )

    def _validator(self, schema: JsonObject) -> jsonschema_rs.Draft202012Validator:
        try:
            return jsonschema_rs.Draft202012Validator(
                _plain_object(schema),
                validate_formats=False,
                offline=True,
                registry=self.__registry,
            )
        except jsonschema_rs.ValidationError as error:
            if isinstance(error.kind, jsonschema_rs.ValidationErrorKind.Referencing):
                raise LlmResponseError(
                    details=_reason(_REFERENCE_KEYWORD, _UNRESOLVABLE_REFERENCE_REASON)
                ) from error
            raise LlmResponseError(
                details=_reason(
                    schema_keyword_at(list(error.instance_path)),
                    _INVALID_SCHEMA_REASON,
                )
            ) from error

    def _loads(self, text: str) -> object:
        try:
            value: object = loads(text, parse_constant=self._reject_json_constant)
        except JSONDecodeError as error:
            raise LlmResponseError from error
        return value

    def _reject_json_constant(self, value: str) -> Never:
        _ = value
        raise LlmResponseError


def _reason(keyword: str | None, reason: str) -> JsonObject:
    """Name a rejected keyword and reason without copying schema values."""
    return {_SCHEMA_KEYWORD_DETAIL: keyword, _SCHEMA_REASON_DETAIL: reason}


def _plain_object(value: JsonObject) -> dict[str, PlainJson]:
    """Copy a framework JSON object into the form the validator reads."""
    return {key: _plain_json(item) for key, item in value.items()}


def _plain_json(value: JsonValue) -> PlainJson:
    """Copy framework JSON into the list-and-dict form the validator reads."""
    if isinstance(value, Mapping):
        return _plain_object(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_plain_json(item) for item in value]
    return value
