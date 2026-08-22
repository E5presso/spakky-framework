"""Tests for provider-neutral JSON and tool validation."""

from math import inf, nan

import pytest
from pydantic import BaseModel
from spakky.agent import (
    JsonSchemaConstraint,
    JsonValue,
    ModelToolSpec,
    ToolCallingSpec,
)

from spakky.plugins.llm.codec import LlmJsonCodec
from spakky.plugins.llm.error import LlmResponseError
from spakky.agent.structured_output import _structured_output_contract


class _NestedCodecValue(BaseModel):
    value: int


class _NestedCodecAnswer(BaseModel):
    nested: _NestedCodecValue


def test_codec_accepts_inlined_nested_contract_and_rejects_all_extras() -> None:
    """Core normalized nested schemas stay inside the portable codec subset."""
    constraint = _structured_output_contract(_NestedCodecAnswer).spec.constraint
    codec = LlmJsonCodec()

    assert codec.decode_value('{"nested":{"value":1}}', constraint) == {
        "nested": {"value": 1}
    }
    with pytest.raises(LlmResponseError):
        codec.decode_value('{"nested":{"value":1,"extra":true}}', constraint)
    with pytest.raises(LlmResponseError):
        codec.decode_value('{"nested":{"value":1},"extra":true}', constraint)


def test_codec_decodes_json_objects_and_structured_values() -> None:
    """JSON text is copied into the framework surface and schema-validated."""
    codec = LlmJsonCodec()
    constraint = JsonSchemaConstraint(
        schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
    )

    assert codec.decode_object("") == {}
    assert codec.decode_object('{"answer":"ok"}', constraint) == {"answer": "ok"}
    assert codec.decode_value('{"answer":"ok"}', constraint) == {"answer": "ok"}
    assert codec.to_value([1, {"nested": True}]) == (1, {"nested": True})


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        ("decode_object", "not-json"),
        ("decode_object", "[]"),
        ("decode_value", ""),
        ("decode_value", "NaN"),
        ("decode_value", "Infinity"),
        ("decode_value", "-Infinity"),
        ("to_object", []),
        ("to_object", {1: "bad-key"}),
        ("to_value", nan),
        ("to_value", inf),
        ("to_value", b"not-json"),
        ("to_value", object()),
    ],
)
def test_codec_rejects_invalid_provider_json(operation: str, value: object) -> None:
    """Malformed or non-JSON provider values never cross the adapter boundary."""
    codec = LlmJsonCodec()
    constraint = JsonSchemaConstraint(schema={})

    with pytest.raises(LlmResponseError):
        if operation == "decode_object":
            codec.decode_object(str(value))
        elif operation == "decode_value":
            codec.decode_value(str(value), constraint)
        elif operation == "to_object":
            codec.to_object(value)
        else:
            codec.to_value(value)


def test_codec_indexes_and_resolves_tool_constraints() -> None:
    """Tool names map to exactly one declared schema."""
    codec = LlmJsonCodec()
    constraint = JsonSchemaConstraint(schema={"type": "object"})
    tools = ToolCallingSpec(
        tools=(ModelToolSpec(name="lookup", parameters=constraint),)
    )
    constraints = codec.tool_constraints(tools)

    assert codec.tool_constraints(None) is None
    assert codec.tool_constraint("lookup", constraints) == constraint
    with pytest.raises(LlmResponseError):
        codec.tool_constraint("anything", None)
    with pytest.raises(LlmResponseError):
        codec.tool_constraint("missing", constraints)


def test_codec_rejects_duplicate_tool_names() -> None:
    """Provider tool responses cannot rely on an ambiguous schema map."""
    tool = ModelToolSpec(
        name="duplicate",
        parameters=JsonSchemaConstraint(schema={"type": "object"}),
    )

    with pytest.raises(LlmResponseError):
        LlmJsonCodec().tool_constraints(ToolCallingSpec(tools=(tool, tool)))


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        ("ok", {"type": "string"}),
        (2, {"type": "integer"}),
        (2.5, {"type": "number"}),
        (True, {"type": "boolean"}),
        (None, {"type": "null"}),
        ("a", {"enum": ["a", "b"]}),
        (1, {"enum": [1.0]}),
        ({"items": [1, True]}, {"enum": [{"items": [1.0, True]}]}),
        (2, {"anyOf": [{"type": "string"}, {"type": "integer"}]}),
        ([1, 2], {"type": "array", "items": {"type": "integer"}}),
        (
            ["a", 2],
            {
                "type": "array",
                "prefixItems": [{"type": "string"}, {"type": "integer"}],
            },
        ),
        ([], {"type": "array", "prefixItems": [{"type": "string"}]}),
        (
            [1],
            {
                "type": "array",
                "prefixItems": [{"type": "integer"}],
                "items": False,
            },
        ),
        (
            [1, "tail"],
            {
                "type": "array",
                "prefixItems": [{"type": "integer"}],
                "items": {"type": "string"},
            },
        ),
        ([1], {"type": "array", "items": True}),
        (
            "ok",
            {
                "$anchor": "answer",
                "$comment": "portable annotation",
                "$id": "urn:answer",
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "default": "ok",
                "deprecated": False,
                "description": "Answer",
                "examples": ["ok"],
                "readOnly": True,
                "title": "Answer",
                "type": "string",
                "writeOnly": False,
            },
        ),
        (
            {"extra": 3},
            {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            },
        ),
        ({"extra": 3}, {"type": "object"}),
        ([1, 2], {"type": "array"}),
    ],
)
def test_codec_accepts_supported_schema_shapes(
    value: JsonValue,
    schema: dict[str, JsonValue],
) -> None:
    """Portable JSON Schema primitives, unions, arrays, and objects are accepted."""
    LlmJsonCodec().validate(value, schema)


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        (1, {"type": "string"}),
        (True, {"type": "integer"}),
        (True, {"type": "number"}),
        ("true", {"type": "boolean"}),
        (0, {"type": "null"}),
        ("c", {"enum": ["a", "b"]}),
        (True, {"enum": [1]}),
        (1, {"enum": [True]}),
        ({"items": [1, True]}, {"enum": [{"items": [1, 1]}]}),
        ({"x": 1}, {"enum": [{"y": 1}]}),
        (1, {"enum": [{}]}),
        ([], {"enum": [{}]}),
        (None, {"enum": [False]}),
        ("1", {"enum": [1]}),
        ("a", {"enum": "a"}),
        (False, {"anyOf": [{"type": "string"}, {"type": "integer"}]}),
        (False, {"anyOf": "invalid"}),
        (False, {"anyOf": ["invalid"]}),
        (False, {"anyOf": []}),
        (
            1,
            {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "string", "minLength": 2},
                ]
            },
        ),
        (1, {"anyOf": [{"type": "integer"}], "type": "string"}),
        ("x", {"type": "string", "minLength": 5}),
        ("x", {"oneOf": [{"type": "integer"}]}),
        (3, {"type": "integer", "minimum": 10}),
        ("x", {"type": None}),
        ({}, {"properties": {}}),
        ([], {"items": True}),
        ("x", {"enum": []}),
        ([], {"type": "object"}),
        ({}, {"type": "object", "required": ["answer"]}),
        ({}, {"type": "object", "required": "answer"}),
        ({}, {"type": "object", "properties": []}),
        ({}, {"type": "object", "properties": {"x": "invalid"}}),
        ({"x": 1}, {"type": "object", "additionalProperties": False}),
        (
            {"x": "bad"},
            {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            },
        ),
        ({"x": 1}, {"type": "object", "additionalProperties": "invalid"}),
        ({}, {"type": "object", "additionalProperties": None}),
        (
            {"x": 1},
            {"type": "object", "properties": {"x": "invalid"}},
        ),
        ({}, {"type": "object", "required": [1]}),
        ({}, {"type": "object", "required": ["x", "x"]}),
        ({}, {"type": "object", "required": None}),
        ({}, {"type": "array"}),
        ([], {"type": "array", "minItems": 1}),
        ([1, 2], {"type": "array", "maxItems": 1}),
        ([], {"type": "array", "items": "invalid"}),
        ([], {"type": "array", "items": None}),
        (["x"], {"type": "array", "items": {"type": "integer"}}),
        ([], {"type": "array", "prefixItems": "invalid"}),
        ([1], {"type": "array", "prefixItems": ["invalid"]}),
        ([], {"type": "array", "prefixItems": ["invalid"]}),
        ([1], {"type": "array", "items": False}),
        (
            [1, "unexpected"],
            {
                "type": "array",
                "prefixItems": [{"type": "integer"}],
                "items": False,
            },
        ),
        (
            [1, "unexpected"],
            {
                "type": "array",
                "prefixItems": [{"type": "integer"}],
                "items": {"type": "integer"},
            },
        ),
        ([], {"type": "array", "minItems": "invalid"}),
        ([], {"type": "array", "minItems": None}),
        ([], {"type": "array", "minItems": -1}),
        ([], {"type": "array", "maxItems": "invalid"}),
        ([], {"type": "array", "maxItems": None}),
        ([], {"type": "array", "maxItems": -1}),
        ([], {"type": "array", "minItems": 2, "maxItems": 1}),
        ("value", {"type": 1}),
        ("value", {"type": "not-a-json-schema-type"}),
    ],
)
def test_codec_rejects_schema_violations(
    value: JsonValue,
    schema: dict[str, JsonValue],
) -> None:
    """Schema mismatches and malformed portable schemas fail closed."""
    with pytest.raises(LlmResponseError):
        LlmJsonCodec().validate(value, schema)
