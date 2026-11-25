"""Tests for provider wire copies of JSON Schema 2020-12 schemas."""

from json import loads

import pytest
from spakky.agent import JsonObject, JsonValue

from spakky.plugins.llm.schema_wire import (
    anthropic_strict_schema,
    gemini_schema,
    openai_strict_schema,
    structured_output_instruction,
)


def test_openai_strict_schema_expect_closed_required_and_widened() -> None:
    """``not`` and ``dependentRequired`` are left out; ``oneOf`` becomes ``anyOf``."""
    schema: JsonObject = {
        "type": "object",
        "title": "Order",
        "properties": {
            "code": {"type": "string", "pattern": "^[A-Z]+$", "not": {"const": "X"}},
            "item": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
            "tags": {"type": "array", "items": True, "minItems": 2},
        },
        "dependentRequired": {"code": ["item"]},
        "$defs": {"unused": {"type": "object", "properties": {}}},
    }

    assert openai_strict_schema(schema) == {
        "type": "object",
        "title": "Order",
        "properties": {
            "code": {"type": "string", "pattern": "^[A-Z]+$"},
            "item": {"anyOf": ({"type": "integer"}, {"type": "string"})},
            "tags": {"type": "array", "items": True, "minItems": 2},
        },
        "$defs": {
            "unused": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
                "required": (),
            }
        },
        "additionalProperties": False,
        "required": ("code", "item", "tags"),
    }


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "allOf": [{"properties": {"a": {}}}]},
        {"type": "object", "if": {"required": ["a"]}, "then": {"required": ["b"]}},
        {"type": "object", "properties": {"a": {"dependentSchemas": {"x": {}}}}},
        {"type": "object", "additionalProperties": {"type": "integer"}},
        {"type": "object", "properties": {"a": {"$ref": "https://example.test/a"}}},
        {"type": "object", "properties": {"a": {"$ref": "#/properties/b"}}},
        {"type": "array", "items": {"type": "string"}},
        {"anyOf": [{"type": "object"}]},
        {"type": "object", "anyOf": [{"properties": {}}]},
        {"type": "object", "properties": []},
        {"type": "object", "properties": {"a": 5}},
        {"type": "object", "properties": {"a": {"anyOf": "invalid"}}},
        {"type": "object", "properties": {"a": {"$ref": 5}}},
    ],
)
def test_openai_strict_schema_unrepresentable_expect_none(schema: JsonObject) -> None:
    """Schemas strict mode cannot hold, even wider, return ``None``."""
    assert openai_strict_schema(schema) is None


def test_openai_strict_schema_keeps_root_recursion() -> None:
    """OpenAI strict mode documents recursion through ``#`` and ``$defs``."""
    schema: JsonObject = {
        "type": "object",
        "properties": {"child": {"anyOf": [{"$ref": "#"}, {"type": "null"}]}},
    }

    wire = openai_strict_schema(schema)

    assert wire is not None
    assert wire["properties"] == {"child": {"anyOf": ({"$ref": "#"}, {"type": "null"})}}


def test_openai_strict_schema_with_any_of_and_one_of_expect_one_of_left_out() -> None:
    """Leaving out ``oneOf`` next to ``anyOf`` only widens the schema."""
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "v": {
                "anyOf": [{"type": "integer"}],
                "oneOf": [{"minimum": 1}, {"maximum": 0}],
            }
        },
    }

    wire = openai_strict_schema(schema)

    assert wire is not None
    assert wire["properties"] == {"v": {"anyOf": ({"type": "integer"},)}}


def test_anthropic_strict_schema_expect_documented_limits_applied() -> None:
    """Unsupported constraints are left out and ``minItems`` is capped at 1."""
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "minimum": 1, "maximum": 9, "multipleOf": 1},
            "name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 9,
                "format": "email",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 5,
            },
            "one": {"type": "array", "minItems": 1, "uniqueItems": True},
            "kind": {"enum": ["a", 1, None, True]},
            "shape": {"enum": [{"x": 1}, "a"]},
            "point": {"const": [1, 2]},
            "label": {"const": "fixed"},
        },
        "required": ["count"],
    }

    assert anthropic_strict_schema(schema) == {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "name": {"type": "string", "format": "email"},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "one": {"type": "array", "minItems": 1},
            "kind": {"enum": ["a", 1, None, True]},
            "shape": {},
            "point": {},
            "label": {"const": "fixed"},
        },
        "required": ["count"],
        "additionalProperties": False,
    }


def test_anthropic_strict_schema_moves_any_of_siblings_into_branches() -> None:
    """``anyOf`` next to ``type`` keeps its meaning with siblings in each branch."""
    schema: JsonObject = {
        "$defs": {"id": {"type": "string"}},
        "description": "Either form",
        "type": "object",
        "properties": {"id": {"$ref": "#/$defs/id"}},
        "anyOf": [{"required": ["id"]}, {"maxProperties": 0}],
    }

    assert anthropic_strict_schema(schema) == {
        "$defs": {"id": {"type": "string"}},
        "description": "Either form",
        "anyOf": (
            {
                "type": "object",
                "properties": {"id": {"$ref": "#/$defs/id"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"id": {"$ref": "#/$defs/id"}},
                "maxProperties": 0,
                "additionalProperties": False,
            },
        ),
    }


def test_anthropic_strict_schema_keeps_annotation_only_any_of() -> None:
    """``anyOf`` with only annotations beside it is already accepted."""
    schema: JsonObject = {
        "title": "Value",
        "anyOf": [{"type": "string"}, {"type": "null"}],
    }

    assert anthropic_strict_schema(schema) == {
        "title": "Value",
        "anyOf": ({"type": "string"}, {"type": "null"}),
    }


@pytest.mark.parametrize(
    "schema",
    [
        {
            "type": "object",
            "properties": {"n": {"anyOf": [{"$ref": "#"}, {"type": "null"}]}},
        },
        {
            "$defs": {
                "a": {"type": "object", "properties": {"b": {"$ref": "#/$defs/b"}}},
                "b": {"type": "object", "properties": {"a": {"$ref": "#/$defs/a"}}},
            },
            "$ref": "#/$defs/a",
        },
        {"type": "string", "anyOf": [{"type": "string"}]},
        {"type": "string", "anyOf": [True]},
        {"type": "object", "additionalProperties": {"type": "string"}},
        {"$defs": [], "type": "object"},
        {"anyOf": 5},
        {"properties": 5},
        {
            "type": "object",
            "properties": {"default": {"$ref": "#/$defs/n"}},
            "$defs": {
                "n": {"type": "object", "properties": {"enum": {"$ref": "#/$defs/n"}}}
            },
        },
        {
            "$ref": "#/$defs/a",
            "$defs": {
                "a": {
                    "type": "object",
                    "properties": {"b": {"$ref": "#/$defs/a/properties/b"}},
                }
            },
        },
        {"if": {"properties": {"a": {"maxLength": 3}}}, "then": {"required": ["b"]}},
        {
            "allOf": [
                {"type": "object", "properties": {"a": {}}},
                {"type": "object", "properties": {"b": {}}},
            ]
        },
        {"type": "object", "dependentSchemas": {"a": {"required": ["b"]}}},
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "anyOf": [{"type": "object", "properties": {"b": {}}}],
        },
    ],
)
def test_anthropic_strict_schema_unrepresentable_expect_none(
    schema: JsonObject,
) -> None:
    """Recursion, merge conflicts, and open maps cannot go strict to Claude."""
    assert anthropic_strict_schema(schema) is None


def test_anthropic_strict_schema_with_acyclic_definitions_expect_kept() -> None:
    """Definitions that refer to each other without a cycle stay as written."""
    schema: JsonObject = {
        "$defs": {
            "a": {
                "type": "object",
                "properties": {"b": {"$ref": "#/$defs/b"}, "c": {"$ref": "#/$defs/c"}},
            },
            "b": {"type": "object", "properties": {"d": {"$ref": "#/$defs/d"}}},
            "c": {"type": "object", "properties": {"d": {"$ref": "#/$defs/d"}}},
            "d": {"type": "string"},
        },
        "$ref": "#/$defs/a",
    }

    wire = anthropic_strict_schema(schema)

    assert wire is not None
    assert wire["$ref"] == "#/$defs/a"


def test_gemini_schema_expect_documented_keywords_only() -> None:
    """Gemini keeps its documented keywords; every other keyword is left out."""
    schema: JsonObject = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "code": {"type": "string", "pattern": "^a", "minLength": 1, "default": "a"},
            "kind": {"const": "fixed", "enum": ["fixed", "other"]},
            "pick": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
            "link": {"$ref": "https://example.test/remote"},
            "self": {"$ref": "#"},
        },
        "patternProperties": {"^x-": {"type": "string"}},
        "allOf": [{"required": ["code"]}],
        "unevaluatedProperties": False,
    }

    assert gemini_schema(schema) == {
        "type": "object",
        "properties": {
            "code": {"type": "string", "minLength": 1},
            "kind": {"enum": ("fixed",)},
            "pick": {"anyOf": ({"type": "integer"}, {"type": "string"})},
            "link": {},
            "self": {"$ref": "#"},
        },
    }


def test_structured_output_instruction_expect_schema_as_compact_json() -> None:
    """The fallback instruction carries the full schema as JSON."""
    schema: dict[str, JsonValue] = {"type": "object", "minProperties": 1}

    instruction = structured_output_instruction(schema)
    prefix, _, encoded = instruction.partition("\n")

    assert prefix.startswith("Respond with only one JSON value")
    assert loads(encoded) == schema


def test_anthropic_strict_schema_dropped_contains_expect_unevaluated_items_dropped() -> (
    None
):
    """``unevaluatedItems`` reads ``contains``, so it leaves with it."""
    schema: JsonObject = {
        "type": "array",
        "contains": {"type": "string"},
        "unevaluatedItems": False,
    }

    assert anthropic_strict_schema(schema) == {"type": "array"}


@pytest.mark.parametrize(
    "schema",
    [
        {
            "$defs": {"x": {"type": "object", "properties": {"b": {}}}},
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "anyOf": [{"$ref": "#/$defs/x"}],
        },
        {
            "$defs": {"x": {"type": "object", "properties": {"b": {}}}},
            "$ref": "#/$defs/x",
            "properties": {"a": {"type": "string"}},
        },
    ],
)
def test_anthropic_strict_schema_closed_reference_beside_properties_expect_none(
    schema: JsonObject,
) -> None:
    """A closed ``$ref`` target beside listed properties would forbid them."""
    assert anthropic_strict_schema(schema) is None


def test_anthropic_strict_schema_unevaluated_beside_reference_expect_dropped() -> None:
    """``unevaluatedItems`` reads the ``$ref`` target, which may be widened."""
    schema: JsonObject = {
        "$defs": {"x": {"type": "array", "contains": {"type": "string"}}},
        "$ref": "#/$defs/x",
        "unevaluatedItems": False,
    }

    assert anthropic_strict_schema(schema) == {
        "$defs": {"x": {"type": "array"}},
        "$ref": "#/$defs/x",
    }


def test_openai_strict_schema_object_branch_beside_properties_expect_none() -> None:
    """Closing an object branch would forbid the properties listed beside it."""
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "v": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "anyOf": [{"type": "object", "properties": {"b": {}}}],
            }
        },
    }

    assert openai_strict_schema(schema) is None


def test_gemini_schema_dropped_pattern_properties_expect_additional_properties_dropped() -> (
    None
):
    """``additionalProperties`` reads ``patternProperties``, so it leaves with it."""
    schema: JsonObject = {
        "type": "object",
        "patternProperties": {"^x": {"type": "integer"}},
        "additionalProperties": False,
    }

    assert gemini_schema(schema) == {"type": "object"}


def test_gemini_schema_foreign_reference_in_prefix_expect_empty_schema() -> None:
    """A foreign ``$ref`` leaves an empty prefix schema; ``items`` stays."""
    schema: JsonObject = {
        "type": "array",
        "prefixItems": [{"$ref": "https://example.test/first"}],
        "items": False,
    }

    assert gemini_schema(schema) == {
        "type": "array",
        "prefixItems": ({},),
        "items": False,
    }


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("#", True),
        ("#/$defs/name", True),
        ("#/$defs/", False),
        ("#/$defs/name/properties/a", False),
        ("#/properties/a", False),
    ],
)
def test_local_reference_expect_root_or_single_definition(
    reference: str,
    expected: bool,
) -> None:
    """Only ``#`` and one ``$defs`` entry count as provider-safe references."""
    schema: JsonObject = {"type": "object", "properties": {"a": {"$ref": reference}}}

    assert (openai_strict_schema(schema) is not None) is expected
