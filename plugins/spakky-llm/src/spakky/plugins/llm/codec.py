"""Provider-neutral JSON and tool-call validation helpers."""

from collections.abc import Mapping, Sequence
from json import JSONDecodeError, loads
from math import isfinite
from typing import Never

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
        schema_type = self._optional_string(schema.get("type"))
        if schema_type is None:
            return
        if schema_type == "object":
            self._validate_object(value, schema)
            return
        if schema_type == "array":
            self._validate_array(value, schema)
            return
        if schema_type == "string" and not isinstance(value, str):
            raise LlmResponseError
        if schema_type == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise LlmResponseError
        if schema_type == "number" and (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or (isinstance(value, float) and not isfinite(value))
        ):
            raise LlmResponseError
        if schema_type == "boolean" and not isinstance(value, bool):
            raise LlmResponseError
        if schema_type == "null" and value is not None:
            raise LlmResponseError

    def _validate_schema_shape(self, schema: JsonObject) -> None:
        for keyword in schema:
            if keyword not in _SUPPORTED_SCHEMA_KEYWORDS:
                raise LlmResponseError
        schema_type = self._optional_string(schema.get("type"))
        if "type" in schema and schema_type is None:
            raise LlmResponseError
        if schema_type is not None and schema_type not in _SUPPORTED_SCHEMA_TYPES:
            raise LlmResponseError
        schema_keywords = frozenset(schema)
        if schema_keywords & _OBJECT_SCHEMA_KEYWORDS and schema_type != "object":
            raise LlmResponseError
        if schema_keywords & _ARRAY_SCHEMA_KEYWORDS and schema_type != "array":
            raise LlmResponseError

        if "anyOf" in schema:
            alternatives = schema["anyOf"]
            alternative_schemas = self._sequence(alternatives)
            if len(alternative_schemas) == 0:
                raise LlmResponseError
            for alternative in alternative_schemas:
                self._validate_schema_shape(self.to_object(alternative))

        if "enum" in schema:
            enum_values = self._sequence(schema["enum"])
            if len(enum_values) == 0:
                raise LlmResponseError

        if "properties" in schema:
            properties = schema["properties"]
            for property_schema in self.to_object(properties).values():
                self._validate_schema_shape(self.to_object(property_schema))

        if "required" in schema:
            self._required_names(schema["required"])

        if "additionalProperties" in schema:
            additional_properties = schema["additionalProperties"]
            if additional_properties is not True and additional_properties is not False:
                self._validate_schema_shape(self.to_object(additional_properties))

        if "prefixItems" in schema:
            prefix_items = schema["prefixItems"]
            for item_schema in self._sequence(prefix_items):
                self._validate_schema_shape(self.to_object(item_schema))

        if "items" in schema:
            item_schema = schema["items"]
            if item_schema is not True and item_schema is not False:
                self._validate_schema_shape(self.to_object(item_schema))

        min_items = self._optional_nonnegative_int(schema.get("minItems"))
        max_items = self._optional_nonnegative_int(schema.get("maxItems"))
        if "minItems" in schema and min_items is None:
            raise LlmResponseError
        if "maxItems" in schema and max_items is None:
            raise LlmResponseError
        if min_items is not None and max_items is not None and min_items > max_items:
            raise LlmResponseError

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
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        if not isinstance(value, Mapping):
            raise LlmResponseError
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
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise LlmResponseError
        min_items = self._optional_nonnegative_int(schema.get("minItems"))
        if min_items is not None and len(value) < min_items:
            raise LlmResponseError
        max_items = self._optional_nonnegative_int(schema.get("maxItems"))
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

    def _optional_string(self, value: JsonValue | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise LlmResponseError
        return value

    def _optional_nonnegative_int(self, value: JsonValue | None) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise LlmResponseError
        return value
