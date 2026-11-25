"""Tests for declaration-time typed structured-output contracts."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import inf
from typing import NotRequired, TypedDict, cast

import pytest
from pydantic import BaseModel, ConfigDict, Field

from spakky.agent import (
    AgentDefinitionError,
    AgentExecutionSpec,
    JsonObject,
    JsonValue,
)
from spakky.agent.structured_output import (
    _json_value,
    _normalize_schema_node,
    _portable_schema,
    _structured_output_contract,
)


class NestedAnswer(BaseModel):
    """Nested model used to prove local refs are inlined strictly."""

    value: int


class ModelAnswer(BaseModel):
    """BaseModel output with a schema-valid default."""

    nested: NestedAnswer
    note: str = "default-note"


@dataclass
class DataclassAnswer:
    """Standard dataclass output with a schema-valid default."""

    value: int
    note: str = "default-note"


class TypedDictAnswer(TypedDict):
    """TypedDict output with one optional field."""

    value: int
    note: NotRequired[str]


class CollectionAnswer(BaseModel):
    values: list[int]
    labels: dict[str, int]


@pytest.mark.parametrize(
    ("output_type", "payload", "expected_type"),
    [
        (ModelAnswer, {"nested": {"value": 1}}, ModelAnswer),
        (DataclassAnswer, {"value": 1}, DataclassAnswer),
        (TypedDictAnswer, {"value": 1}, dict),
    ],
)
def test_structured_contract_materializes_supported_types_with_optional_defaults(
    output_type: type[object],
    payload: JsonObject,
    expected_type: type[object],
) -> None:
    """Supported output classes materialize exactly without requiring defaults."""
    contract = _structured_output_contract(output_type)

    materialized = contract.materialize(payload)
    dumped = cast(Mapping[str, JsonValue], contract.dump(materialized))

    assert isinstance(materialized, expected_type)
    assert dumped["value" if output_type is not ModelAnswer else "nested"]


def test_structured_contract_inlines_nested_refs_and_forbids_object_extras() -> None:
    """Nested Pydantic refs become portable closed object schemas."""
    contract = _structured_output_contract(ModelAnswer)
    schema = contract.spec.constraint.schema
    properties = cast(Mapping[str, JsonValue], schema["properties"])
    nested = cast(Mapping[str, JsonValue], properties["nested"])

    assert "$defs" not in schema
    assert "$ref" not in nested
    assert schema["additionalProperties"] is False
    assert nested["additionalProperties"] is False


@pytest.mark.parametrize(
    "output_type",
    [ModelAnswer, DataclassAnswer, TypedDictAnswer],
)
def test_structured_contract_rejects_extra_missing_and_wrong_typed_values(
    output_type: type[object],
) -> None:
    """No supported materializer may coerce types or silently discard keys."""
    contract = _structured_output_contract(output_type)
    valid = {"nested": {"value": 1}} if output_type is ModelAnswer else {"value": 1}
    with pytest.raises(AgentDefinitionError):
        contract.materialize({**valid, "extra": True})
    with pytest.raises(AgentDefinitionError):
        contract.materialize({})
    wrong = {"nested": {"value": "1"}} if output_type is ModelAnswer else {"value": "1"}
    with pytest.raises(AgentDefinitionError):
        contract.materialize(wrong)


def test_execution_spec_rejects_unsupported_output_classes() -> None:
    """Classes that are not BaseModel, dataclass, or TypedDict fail at declaration."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(output_type=str)


class DateAnswer(BaseModel):
    """Output whose schema carries a ``format`` annotation."""

    created_at: datetime


class RecursiveAnswer(BaseModel):
    """Self-referencing output that needs ``$defs`` to stay finite."""

    child: "RecursiveAnswer | None" = None


class ConstrainedValue(BaseModel):
    """Nested model with a numeric constraint."""

    value: int = Field(ge=1)


class ConstrainedAnswer(BaseModel):
    """Output whose schema uses keywords outside the old portable subset."""

    nested: ConstrainedValue = Field(description="Nested value")
    code: str = Field(min_length=2, pattern="^[A-Z]+$")


def test_structured_contract_keeps_format_annotation_and_materializes() -> None:
    """A datetime field keeps ``format`` and materializes from its JSON string."""
    contract = _structured_output_contract(DateAnswer)
    properties = cast(
        Mapping[str, JsonValue], contract.spec.constraint.schema["properties"]
    )

    result = contract.materialize({"created_at": "2026-01-02T03:04:05Z"})

    assert properties["created_at"] == {
        "format": "date-time",
        "title": "Created At",
        "type": "string",
    }
    assert isinstance(result, DateAnswer)


def test_structured_contract_keeps_recursive_reference_in_definitions() -> None:
    """A recursive model refers to itself through ``$defs`` instead of failing."""
    contract = _structured_output_contract(RecursiveAnswer)
    schema = contract.spec.constraint.schema
    properties = cast(Mapping[str, JsonValue], schema["properties"])
    definitions = cast(Mapping[str, Mapping[str, JsonValue]], schema["$defs"])

    result = contract.materialize({"child": {"child": None}})

    assert properties["child"] == {
        "anyOf": ({"$ref": "#/$defs/RecursiveAnswer"}, {"type": "null"}),
        "default": None,
    }
    assert definitions["RecursiveAnswer"]["properties"] == properties
    assert definitions["RecursiveAnswer"]["additionalProperties"] is False
    assert isinstance(result, RecursiveAnswer)


def test_structured_contract_keeps_constraint_keywords_and_reference_annotations() -> (
    None
):
    """Constraint keywords stay, and a described reference is inlined with it."""
    schema = _structured_output_contract(ConstrainedAnswer).spec.constraint.schema
    properties = cast(Mapping[str, Mapping[str, JsonValue]], schema["properties"])

    assert properties["code"]["minLength"] == 2
    assert properties["code"]["pattern"] == "^[A-Z]+$"
    assert properties["nested"]["description"] == "Nested value"
    assert properties["nested"]["additionalProperties"] is False
    assert (
        cast(Mapping[str, Mapping[str, JsonValue]], properties["nested"]["properties"])[
            "value"
        ]["minimum"]
        == 1
    )


def test_structured_contract_is_cached_per_output_class() -> None:
    """Declaration and request construction reuse one compiled TypeAdapter/schema."""
    assert _structured_output_contract(ModelAnswer) is _structured_output_contract(
        ModelAnswer
    )


def test_structured_contract_preserves_nested_collections_exactly() -> None:
    contract = _structured_output_contract(CollectionAnswer)
    result = contract.materialize({"values": [1, 2], "labels": {"a": 1}})
    assert isinstance(result, CollectionAnswer)
    assert result.values == [1, 2]


def test_structured_contract_detects_serializer_key_loss_and_dump_failure() -> None:
    class ExcludedAnswer(BaseModel):
        value: str = Field(exclude=True)

    contract = _structured_output_contract(ExcludedAnswer)
    with pytest.raises(AgentDefinitionError, match="changed its JSON shape"):
        contract.materialize({"value": "hidden"})
    with pytest.raises(AgentDefinitionError, match="could not be serialized"):
        contract.dump(object())


def test_structured_contract_wraps_pydantic_schema_generation_failure() -> None:
    class ArbitraryValue:
        pass

    class ArbitraryAnswer(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        value: ArbitraryValue

    with pytest.raises(AgentDefinitionError, match="cannot produce"):
        AgentExecutionSpec(output_type=ArbitraryAnswer)


@pytest.mark.parametrize(
    ("value", "defs"),
    [
        (inf, {}),
        (object(), {}),
        ({1: "bad"}, {}),
        ({"$ref": "https://example.test/schema"}, {}),
        ({"$ref": 1}, {}),
        ({"$ref": "#/$defs/missing"}, {}),
        ({"$ref": "#/$defs/Primitive"}, {"Primitive": "string"}),
        ({"properties": []}, {}),
        (
            {"$ref": "#/$defs/Item", "allOf": {"minItems": 1}},
            {"Item": {"type": "array"}},
        ),
    ],
)
def test_structured_schema_normalizer_rejects_invalid_nodes(
    value: object,
    defs: Mapping[str, object],
) -> None:
    """Non-JSON values and references outside local definitions are rejected."""
    with pytest.raises(AgentDefinitionError):
        _normalize_schema_node(value, defs, (), {})


@pytest.mark.parametrize(
    ("value", "defs", "expected"),
    [
        (
            {"$ref": "#/$defs/Item", "minItems": 1},
            {"Item": {"type": "array"}},
            {"minItems": 1, "allOf": ({"type": "array"},)},
        ),
        (
            {"$ref": "#/$defs/Item", "title": "Item", "maxItems": 2},
            {"Item": {"type": "array"}},
            {"title": "Item", "maxItems": 2, "allOf": ({"type": "array"},)},
        ),
        (
            {"$ref": "#/$defs/Item", "allOf": ({"minItems": 1},)},
            {"Item": {"type": "array"}},
            {"allOf": ({"type": "array"}, {"minItems": 1})},
        ),
        (
            {"enum": ({"$ref": "#/$defs/missing"},), "const": {"$ref": "x"}},
            {},
            {"enum": ({"$ref": "#/$defs/missing"},), "const": {"$ref": "x"}},
        ),
        (
            {
                "not": {"$ref": "#/$defs/Name"},
                "patternProperties": {"^x": {"$ref": "#/$defs/Name"}},
            },
            {"Name": {"type": "string"}},
            {
                "not": {"type": "string"},
                "patternProperties": {"^x": {"type": "string"}},
            },
        ),
    ],
)
def test_structured_schema_normalizer_inlines_references_in_any_keyword(
    value: object,
    defs: Mapping[str, object],
    expected: JsonValue,
) -> None:
    """References inline under every subschema keyword but never inside data."""
    assert _normalize_schema_node(value, defs, (), {}) == expected


@pytest.mark.parametrize("raw", [[], {"$defs": []}])
def test_structured_schema_root_and_definitions_must_be_objects(raw: object) -> None:
    with pytest.raises(AgentDefinitionError):
        _portable_schema(raw)


def test_structured_schema_root_reference_must_resolve_to_object() -> None:
    """A root reference to a non-object definition is rejected."""
    with pytest.raises(AgentDefinitionError):
        _portable_schema(
            {"$defs": {"Primitive": "string"}, "$ref": "#/$defs/Primitive"}
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("text", "text"),
        (1, 1),
        (True, True),
        (1.5, 1.5),
        (["text"], ("text",)),
    ],
)
def test_structured_schema_normalizer_preserves_valid_json_nodes(
    value: object,
    expected: JsonValue,
) -> None:
    assert _normalize_schema_node(value, {}, (), {}) == expected


@pytest.mark.parametrize("value", [inf, {1: "bad"}, object()])
def test_structured_json_boundary_rejects_non_json_values(value: object) -> None:
    with pytest.raises(AgentDefinitionError):
        _json_value(value)


def test_structured_json_boundary_accepts_finite_number() -> None:
    assert _json_value(1.5) == 1.5
