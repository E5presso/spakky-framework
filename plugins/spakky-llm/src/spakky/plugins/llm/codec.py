"""Provider-neutral JSON and tool-call validation helpers."""

from collections.abc import Mapping, Sequence
from json import JSONDecodeError, loads
from math import isfinite
from typing import Never, TypeGuard

from spakky.agent import (
    JsonObject,
    JsonSchemaConstraint,
    JsonValue,
    ToolCallingSpec,
)

from spakky.plugins.llm.error import LlmResponseError

_SUPPORTED_SCHEMA_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)
_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$anchor",
        "$comment",
        "$id",
        "$schema",
        "additionalProperties",
        "anyOf",
        "default",
        "deprecated",
        "description",
        "enum",
        "examples",
        "items",
        "maxItems",
        "minItems",
        "prefixItems",
        "properties",
        "readOnly",
        "required",
        "title",
        "type",
        "writeOnly",
    }
)
_OBJECT_SCHEMA_KEYWORDS = frozenset({"additionalProperties", "properties", "required"})
_ARRAY_SCHEMA_KEYWORDS = frozenset({"items", "maxItems", "minItems", "prefixItems"})
_SCHEMA_KEYWORD_DETAIL = "schema_keyword"
"""Error detail key naming the JSON Schema keyword that was rejected."""
_SCHEMA_REASON_DETAIL = "reason"
"""Error detail key naming why the JSON Schema keyword was rejected."""


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


class LlmJsonCodec:
    """Decode provider JSON and validate the portable JSON Schema subset."""

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

    def validate(
        self,
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        """Validate the JSON Schema subset emitted by Spakky agent tooling."""
        normalized_value = self.to_value(value)
        normalized_schema = self.to_object(schema)
        self._validate_schema_shape(normalized_schema)
        self._validate_schema_value(normalized_value, normalized_schema)

    def _validate_schema_value(
        self,
        value: JsonValue,
        schema: JsonObject,
    ) -> None:
        alternatives = schema.get("anyOf")
        if alternatives is not None:
            self._validate_any_of(value, self._sequence(alternatives))
        enum_values = schema.get("enum")
        if enum_values is not None:
            self._validate_enum(value, self._sequence(enum_values))
        schema_types = self._schema_types(schema)
        if schema_types is None:
            return
        if "object" in schema_types and isinstance(value, Mapping):
            self._validate_object(value, schema)
            return
        if "array" in schema_types and self._is_array(value):
            self._validate_array(value, schema)
            return
        if not any(self._matches_type(value, name) for name in schema_types):
            raise LlmResponseError

    def _matches_type(self, value: JsonValue, type_name: str) -> bool:
        if type_name == "object":
            return isinstance(value, Mapping)
        if type_name == "array":
            return self._is_array(value)
        if type_name == "string":
            return isinstance(value, str)
        if type_name == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if type_name == "number":
            return (
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and (not isinstance(value, float) or isfinite(value))
            )
        if type_name == "boolean":
            return isinstance(value, bool)
        return value is None

    def _is_array(self, value: JsonValue) -> TypeGuard[Sequence[JsonValue]]:
        return isinstance(value, Sequence) and not isinstance(value, str)

    def _validate_schema_shape(self, schema: JsonObject) -> None:
        for keyword in schema:
            if keyword not in _SUPPORTED_SCHEMA_KEYWORDS:
                raise self._shape_error(keyword, "unsupported_keyword")
        schema_types = self._schema_types(schema)
        schema_keywords = frozenset(schema)
        object_keywords = schema_keywords & _OBJECT_SCHEMA_KEYWORDS
        if object_keywords and (schema_types is None or "object" not in schema_types):
            raise self._shape_error(min(object_keywords), "requires_object_type")
        array_keywords = schema_keywords & _ARRAY_SCHEMA_KEYWORDS
        if array_keywords and (schema_types is None or "array" not in schema_types):
            raise self._shape_error(min(array_keywords), "requires_array_type")

        if "anyOf" in schema:
            alternative_schemas = self._shape_sequence("anyOf", schema["anyOf"])
            if len(alternative_schemas) == 0:
                raise self._shape_error("anyOf", "empty_list")
            for alternative in alternative_schemas:
                self._validate_schema_shape(self._shape_object("anyOf", alternative))

        if "enum" in schema:
            enum_values = self._shape_sequence("enum", schema["enum"])
            if len(enum_values) == 0:
                raise self._shape_error("enum", "empty_list")

        if "properties" in schema:
            properties = self._shape_object("properties", schema["properties"])
            for property_schema in properties.values():
                self._validate_schema_shape(
                    self._shape_object("properties", property_schema)
                )

        if "required" in schema:
            try:
                self._required_names(schema["required"])
            except LlmResponseError as error:
                raise self._shape_error("required", "invalid_value") from error

        if "additionalProperties" in schema:
            additional_properties = schema["additionalProperties"]
            if additional_properties is not True and additional_properties is not False:
                self._validate_schema_shape(
                    self._shape_object("additionalProperties", additional_properties)
                )

        if "prefixItems" in schema:
            for item_schema in self._shape_sequence(
                "prefixItems", schema["prefixItems"]
            ):
                self._validate_schema_shape(
                    self._shape_object("prefixItems", item_schema)
                )

        if "items" in schema:
            item_schema = schema["items"]
            if item_schema is not True and item_schema is not False:
                self._validate_schema_shape(self._shape_object("items", item_schema))

        min_items = self._shape_item_count(schema, "minItems")
        max_items = self._shape_item_count(schema, "maxItems")
        if min_items is not None and max_items is not None and min_items > max_items:
            raise self._shape_error("minItems", "exceeds_max_items")

    def _schema_types(self, schema: Mapping[str, JsonValue]) -> tuple[str, ...] | None:
        """Read ``type`` as JSON Schema 2020-12 defines it: a string or a unique array."""
        if "type" not in schema:
            return None
        value = schema["type"]
        if isinstance(value, str):
            names: tuple[str, ...] = (value,)
        elif self._is_array(value):
            names = self._type_names(self._sequence(value))
        else:
            raise self._shape_error("type", "invalid_value")
        for name in names:
            if name not in _SUPPORTED_SCHEMA_TYPES:
                raise self._shape_error("type", "unsupported_type")
        return names

    def _type_names(self, values: Sequence[JsonValue]) -> tuple[str, ...]:
        if len(values) == 0:
            raise self._shape_error("type", "empty_list")
        names: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise self._shape_error("type", "invalid_value")
            if value in names:
                raise self._shape_error("type", "duplicate_type")
            names.append(value)
        return tuple(names)

    def _shape_error(self, keyword: str, reason: str) -> LlmResponseError:
        """Name the rejected keyword and reason without copying schema values."""
        return LlmResponseError(
            details={
                _SCHEMA_KEYWORD_DETAIL: keyword,
                _SCHEMA_REASON_DETAIL: reason,
            }
        )

    def _shape_sequence(self, keyword: str, value: JsonValue) -> Sequence[JsonValue]:
        if not self._is_array(value):
            raise self._shape_error(keyword, "invalid_value")
        return self._sequence(value)

    def _shape_object(self, keyword: str, value: JsonValue) -> JsonObject:
        if not isinstance(value, Mapping):
            raise self._shape_error(keyword, "invalid_value")
        return self.to_object(value)

    def _shape_item_count(
        self,
        schema: Mapping[str, JsonValue],
        keyword: str,
    ) -> int | None:
        if keyword not in schema:
            return None
        value = schema[keyword]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise self._shape_error(keyword, "invalid_value")
        return value

    def _loads(self, text: str) -> object:
        try:
            value: object = loads(text, parse_constant=self._reject_json_constant)
        except JSONDecodeError as error:
            raise LlmResponseError from error
        return value

    def _reject_json_constant(self, value: str) -> Never:
        _ = value
        raise LlmResponseError

    def _validate_any_of(
        self,
        value: JsonValue,
        alternatives: Sequence[JsonValue],
    ) -> None:
        for alternative in alternatives:
            try:
                self.validate(value, self.to_object(alternative))
                return
            except LlmResponseError:
                continue
        raise LlmResponseError

    def _validate_enum(
        self,
        value: JsonValue,
        enum_values: Sequence[JsonValue],
    ) -> None:
        if not any(self._json_equal(value, candidate) for candidate in enum_values):
            raise LlmResponseError

    def _json_equal(self, left: JsonValue, right: JsonValue) -> bool:
        if left is None or right is None:
            return left is right
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left == right
        if isinstance(left, str) or isinstance(right, str):
            return isinstance(left, str) and isinstance(right, str) and left == right
        if isinstance(left, int | float) and isinstance(right, int | float):
            return left == right
        if isinstance(left, Mapping):
            if not isinstance(right, Mapping) or left.keys() != right.keys():
                return False
            return all(self._json_equal(item, right[key]) for key, item in left.items())
        if isinstance(left, Sequence):
            if not isinstance(right, Sequence) or len(left) != len(right):
                return False
            return all(
                self._json_equal(left_item, right_item)
                for left_item, right_item in zip(left, right, strict=True)
            )
        return False

    def _validate_object(
        self,
        value: Mapping[str, JsonValue],
        schema: Mapping[str, JsonValue],
    ) -> None:
        required = self._required_names(schema.get("required", ()))
        for required_key in required:
            if required_key not in value:
                raise LlmResponseError
        properties = self.to_object(schema.get("properties", {}))
        additional_properties = schema.get("additionalProperties", True)
        for key, item in value.items():
            property_schema = properties.get(key)
            if property_schema is None:
                self._validate_additional_property(item, additional_properties)
            else:
                self.validate(item, self.to_object(property_schema))

    def _validate_additional_property(
        self,
        value: JsonValue,
        additional_properties: JsonValue,
    ) -> None:
        if additional_properties is False:
            raise LlmResponseError
        if additional_properties is True:
            return
        self.validate(value, self.to_object(additional_properties))

    def _validate_array(
        self,
        value: Sequence[JsonValue],
        schema: Mapping[str, JsonValue],
    ) -> None:
        min_items = self._item_count(schema.get("minItems"))
        if min_items is not None and len(value) < min_items:
            raise LlmResponseError
        max_items = self._item_count(schema.get("maxItems"))
        if max_items is not None and len(value) > max_items:
            raise LlmResponseError
        prefix_items = schema.get("prefixItems")
        prefix_count = 0
        if prefix_items is not None:
            prefix_count = self._validate_prefix_items(value, prefix_items)
        item_schema = schema.get("items")
        if item_schema is None:
            return
        if item_schema is False:
            if len(value) > prefix_count:
                raise LlmResponseError
            return
        if item_schema is True:
            return
        for item in value[prefix_count:]:
            self.validate(item, self.to_object(item_schema))

    def _validate_prefix_items(
        self,
        value: Sequence[JsonValue],
        prefix_items: JsonValue,
    ) -> int:
        normalized_prefix_items = self._sequence(prefix_items)
        for index, item_schema in enumerate(normalized_prefix_items):
            if index < len(value):
                self.validate(value[index], self.to_object(item_schema))
        return len(normalized_prefix_items)

    def _sequence(self, value: JsonValue) -> Sequence[JsonValue]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise LlmResponseError
        return value

    def _required_names(self, value: JsonValue) -> tuple[str, ...]:
        names: list[str] = []
        for name in self._sequence(value):
            if not isinstance(name, str) or name in names:
                raise LlmResponseError
            names.append(name)
        return tuple(names)

    def _item_count(self, value: JsonValue | None) -> int | None:
        """Read an item bound that schema shape validation already accepted."""
        return value if isinstance(value, int) else None
