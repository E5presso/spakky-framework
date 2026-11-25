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

from spakky.plugins.llm.codec import (
    LlmJsonCodec,
    schema_keyword_at,
    schema_type_names,
)
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
        (1, {"anyOf": [{"type": "integer"}], "type": "string"}),
        ("x", {"type": "string", "minLength": 5}),
        ("x", {"oneOf": [{"type": "integer"}]}),
        (3, {"type": "integer", "minimum": 10}),
        ("x", {"type": None}),
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


_NULLABLE_NAME = {"type": ["string", "null"]}
_NULLABLE_PROFILE = {
    "type": ["object", "null"],
    "properties": {"name": _NULLABLE_NAME},
    "required": ["name"],
    "additionalProperties": False,
}
_NULLABLE_TAGS = {
    "type": ["array", "null"],
    "items": {"type": ["string", "integer"]},
    "maxItems": 2,
}


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        ("ok", {"type": ["string", "null"]}),
        (None, {"type": ["string", "null"]}),
        (2, {"type": ["integer", "string"]}),
        (2.5, {"type": ["number"]}),
        (True, {"type": ["boolean", "null"]}),
        ({"name": "x"}, _NULLABLE_PROFILE),
        ({"name": None}, _NULLABLE_PROFILE),
        (None, _NULLABLE_PROFILE),
        (["a", 1], _NULLABLE_TAGS),
        (None, _NULLABLE_TAGS),
        ("a", {"type": ["string", "null"], "enum": ["a", None]}),
        (None, {"type": ["string", "null"], "enum": ["a", None]}),
        (
            {"profile": None, "tags": ["a"]},
            {
                "type": "object",
                "properties": {"profile": _NULLABLE_PROFILE, "tags": _NULLABLE_TAGS},
            },
        ),
        (
            {"profile": {"name": None}},
            {
                "anyOf": [
                    {"type": "string"},
                    {
                        "type": ["object", "null"],
                        "properties": {"profile": _NULLABLE_PROFILE},
                    },
                ]
            },
        ),
    ],
)
def test_codec_accepts_type_union_value_of_any_listed_type(
    value: JsonValue,
    schema: dict[str, JsonValue],
) -> None:
    """A ``type`` array accepts a value whose JSON type is any listed type."""
    LlmJsonCodec().validate(value, schema)


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        (1, {"type": ["string", "null"]}),
        (True, {"type": ["integer", "number"]}),
        ("x", {"type": ["object", "null"]}),
        ({"name": 1}, _NULLABLE_PROFILE),
        ({}, _NULLABLE_PROFILE),
        ({"name": "x", "extra": True}, _NULLABLE_PROFILE),
        ("a", _NULLABLE_TAGS),
        ([True], _NULLABLE_TAGS),
        (["a", "b", "c"], _NULLABLE_TAGS),
        ("b", {"type": ["string", "null"], "enum": ["a", None]}),
        (
            {"profile": {"name": 1}},
            {"type": "object", "properties": {"profile": _NULLABLE_PROFILE}},
        ),
    ],
)
def test_codec_rejects_value_outside_type_union(
    value: JsonValue,
    schema: dict[str, JsonValue],
) -> None:
    """A value outside every listed type, or failing its type's keywords, fails."""
    with pytest.raises(LlmResponseError):
        LlmJsonCodec().validate(value, schema)


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        (
            1,
            {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "string", "minLength": 2},
                ]
            },
        ),
        ({}, {"properties": {}}),
        ([], {"items": True}),
        ("ab", {"type": "string", "minLength": 2, "pattern": "^a"}),
        (3, {"const": 3}),
        (4, {"oneOf": [{"multipleOf": 2}, {"multipleOf": 3}]}),
        ({"a": 1}, {"allOf": [{"required": ["a"]}, {"maxProperties": 1}]}),
        ("x", {"not": {"type": "integer"}}),
        (
            {"kind": "b", "b": 1},
            {
                "if": {"properties": {"kind": {"const": "b"}}},
                "then": {"required": ["b"]},
                "else": {"required": ["a"]},
            },
        ),
        ({"x-1": 1}, {"patternProperties": {"^x-": {"type": "integer"}}}),
        (
            {"a": 1},
            {"properties": {"a": {}}, "unevaluatedProperties": False},
        ),
        ({"a": 1, "b": 2}, {"dependentRequired": {"a": ["b"]}}),
        (
            {"next": {"next": None}},
            {
                "$defs": {
                    "node": {
                        "type": "object",
                        "properties": {
                            "next": {
                                "anyOf": [{"$ref": "#/$defs/node"}, {"type": "null"}]
                            }
                        },
                    }
                },
                "$ref": "#/$defs/node",
            },
        ),
        ("not-an-email", {"type": "string", "format": "email"}),
        ([1, "a"], {"prefixItems": [{"type": "integer"}], "items": {"type": "string"}}),
        ({"x": True}, {"additionalProperties": True}),
        (True, {"properties": {"x": False}}),
    ],
)
def test_codec_accepts_json_schema_2020_12_keywords_expect_valid(
    value: JsonValue,
    schema: dict[str, JsonValue],
) -> None:
    """Keywords outside the old portable subset validate as 2020-12 defines."""
    LlmJsonCodec().validate(value, schema)


@pytest.mark.parametrize(
    ("schema", "keyword", "reason"),
    [
        ({"type": []}, "type", "invalid_schema"),
        ({"type": ["string", "string"]}, "type", "invalid_schema"),
        ({"type": ["string", 1]}, "type", "invalid_schema"),
        ({"type": "date"}, "type", "invalid_schema"),
        ({"type": None}, "type", "invalid_schema"),
        ({"anyOf": []}, "anyOf", "invalid_schema"),
        ({"anyOf": "invalid"}, "anyOf", "invalid_schema"),
        ({"enum": "a"}, "enum", "invalid_schema"),
        ({"properties": []}, "properties", "invalid_schema"),
        ({"properties": {"secret-name": 5}}, "properties", "invalid_schema"),
        ({"properties": {"secret-name": {"type": 5}}}, "type", "invalid_schema"),
        ({"$defs": {"secret-name": {"minimum": "x"}}}, "minimum", "invalid_schema"),
        ({"required": ["x", "x"]}, "required", "invalid_schema"),
        ({"minItems": -1}, "minItems", "invalid_schema"),
        ({"pattern": "(unclosed"}, "pattern", "invalid_schema"),
        ({"$ref": "#/$defs/missing"}, "$ref", "unresolvable_reference"),
        (
            {"$ref": "https://example.test/remote.json"},
            "$ref",
            "unresolvable_reference",
        ),
    ],
)
def test_codec_rejected_schema_expect_keyword_and_reason_only(
    schema: dict[str, JsonValue],
    keyword: str,
    reason: str,
) -> None:
    """A rejected schema names the keyword and reason, never names or values."""
    with pytest.raises(LlmResponseError) as raised:
        LlmJsonCodec().check_schema(schema)

    assert raised.value.details == {"schema_keyword": keyword, "reason": reason}


@pytest.mark.parametrize(
    ("value", "schema", "keyword"),
    [
        (
            {"secret-name": "x"},
            {"properties": {"secret-name": {"minLength": 3}}},
            "minLength",
        ),
        (5, {"type": "string"}, "type"),
        ({}, {"required": ["secret-name"]}, "required"),
        ([1], {"items": False}, "items"),
        ("x", {"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n"}, "type"),
    ],
)
def test_codec_rejected_value_expect_keyword_and_reason_only(
    value: JsonValue,
    schema: dict[str, JsonValue],
    keyword: str,
) -> None:
    """A value mismatch names the failing keyword, never the value or names."""
    with pytest.raises(LlmResponseError) as raised:
        LlmJsonCodec().validate(value, schema)

    assert raised.value.details == {
        "schema_keyword": keyword,
        "reason": "value_mismatch",
    }


def test_codec_external_schema_expect_reference_resolved_without_retrieval() -> None:
    """A registered external schema resolves a ``$ref``; nothing is fetched."""
    codec = LlmJsonCodec({"https://example.test/name.json": {"type": "string"}})
    schema: dict[str, JsonValue] = {"$ref": "https://example.test/name.json"}

    codec.validate("ok", schema)
    with pytest.raises(LlmResponseError):
        codec.validate(1, schema)


def test_codec_invalid_external_schema_expect_reference_error() -> None:
    """An external schema that cannot be registered is rejected at construction."""
    with pytest.raises(LlmResponseError) as raised:
        LlmJsonCodec({"not a uri": {"type": "string"}})

    assert raised.value.details == {
        "schema_keyword": "$ref",
        "reason": "unresolvable_reference",
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (["properties", "type", "minLength"], "minLength"),
        (["properties", "type"], "properties"),
        (["anyOf", 0, "type"], "type"),
        (["$defs", "items"], "$defs"),
        ([0], None),
        ([], None),
    ],
)
def test_schema_keyword_at_expect_last_keyword_not_name(
    path: list[str | int],
    expected: str | None,
) -> None:
    """User-chosen names under name maps are never reported as keywords."""
    assert schema_keyword_at(path) == expected


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "object"}, ("object",)),
        ({"type": ["object", "null"]}, ("object", "null")),
        ({"type": ("array", 1)}, ("array",)),
        ({}, ()),
        ({"type": None}, ()),
    ],
)
def test_schema_type_names_reads_type_without_validation(
    schema: dict[str, JsonValue],
    expected: tuple[str, ...],
) -> None:
    """Wire transforms read the listed type names in declaration order."""
    assert schema_type_names(schema) == expected
