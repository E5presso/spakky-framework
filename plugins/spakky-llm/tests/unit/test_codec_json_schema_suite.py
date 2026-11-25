"""Run the official JSON-Schema-Test-Suite against the codec for draft 2020-12.

The fixtures are the validation tests of
https://github.com/json-schema-org/JSON-Schema-Test-Suite at commit
e2a68a15cd490750fd6b95e604e4054d7d978d1f (MIT license, copied in the fixture
directory). The runner follows the suite README: it keeps test cases whose
``compatibility`` admits 2020-12, skips cases tagged ``format-assertion``
because 2020-12 treats ``format`` as an annotation by default, and registers
each case's ``externalSchemas`` under their retrieval URIs. The ``optional``
and ``proposals`` directories are not copied.
"""

from json import loads
from pathlib import Path

import pytest
from spakky.agent import JsonValue

from spakky.plugins.llm.codec import LlmJsonCodec
from spakky.plugins.llm.error import LlmResponseError

_SUITE_DIRECTORY = Path(__file__).parent / "fixtures" / "json_schema_test_suite"
_DIALECT_RELEASE = 2020
_FORMAT_ASSERTION_TAG = "format-assertion"


def _compatible(compatibility: str | None) -> bool:
    """Apply the suite README's compatibility algorithm to 2020-12."""
    if compatibility is None:
        return True
    compatible = True
    for constraint in compatibility.split(","):
        if constraint.startswith("<="):
            compatible = compatible and _DIALECT_RELEASE <= int(constraint[2:])
        elif constraint.startswith("="):
            compatible = compatible and _DIALECT_RELEASE == int(constraint[1:])
        else:
            compatible = compatible and _DIALECT_RELEASE >= int(constraint)
    return compatible


def _suite_tests() -> list[object]:
    parameters: list[object] = []
    for path in sorted(_SUITE_DIRECTORY.glob("*.json")):
        for case in loads(path.read_text(encoding="utf-8"))["tests"]:
            if not _compatible(case.get("compatibility")):
                continue
            if _FORMAT_ASSERTION_TAG in case.get("tags", ()):
                continue
            for test in case["tests"]:
                parameters.append(
                    pytest.param(
                        case["schema"],
                        case.get("externalSchemas", {}),
                        test["data"],
                        test["valid"],
                        id=f"{path.stem}: {case['description']}: {test['description']}",
                    )
                )
    return parameters


_SUITE_TESTS = _suite_tests()


def _object_schema(schema: JsonValue) -> dict[str, JsonValue]:
    """Write a boolean root schema as its exact object equivalent.

    The codec takes object schemas. ``true`` equals ``{}`` and ``false``
    equals ``{"not": {}}`` in 2020-12, so the verdicts do not change.
    """
    if schema is True:
        return {}
    if schema is False:
        return {"not": {}}
    assert isinstance(schema, dict)
    return schema


def test_suite_fixture_selection_expect_all_required_2020_12_tests() -> None:
    """The runner selects every required 2020-12 test of the pinned suite."""
    assert len(_SUITE_TESTS) == 1305


@pytest.mark.parametrize(
    ("schema", "external_schemas", "data", "valid"),
    _SUITE_TESTS,
)
def test_codec_official_suite_expect_suite_verdict(
    schema: JsonValue,
    external_schemas: dict[str, dict[str, JsonValue]],
    data: JsonValue,
    valid: bool,
) -> None:
    """Each required 2020-12 test validates exactly as the suite expects."""
    codec = LlmJsonCodec(external_schemas)
    object_schema = _object_schema(schema)

    if valid:
        codec.validate(data, object_schema)
    else:
        with pytest.raises(LlmResponseError):
            codec.validate(data, object_schema)
