"""Policy document loader tests."""

import json

import pytest

from spakky.plugins.policy.error import (
    PolicyDocumentLoadError,
    PolicyDocumentValidationError,
)
from spakky.plugins.policy.loader import (
    load_policy_document,
    policy_document_from_mapping,
)
from spakky.plugins.policy.model import ConditionComposition, ConditionOperator


def test_policy_document_from_mapping_canonicalizes_all_sections(policy_document):
    """Mapping input becomes a typed canonical policy document."""
    assert policy_document.version == "2026-06"
    assert policy_document.metadata.name == "authz"
    assert policy_document.metadata.description == "test policy"
    assert policy_document.metadata.labels == ("auth", "policy")
    assert policy_document.subjects[0].claims == (("tier", "gold"),)
    assert policy_document.resources[0].tenant == "tenant:acme"
    assert policy_document.permissions[0].resources == ("article:1",)
    assert policy_document.roles[0].permissions == ("permission:article-read",)
    assert policy_document.scopes[0].permissions == ("permission:article-read",)
    assert policy_document.conditions[0].operator is ConditionOperator.IN
    assert (
        policy_document.policies[2].statements[0].condition.composition
        is ConditionComposition.ANY
    )


def test_policy_document_defaults_metadata_when_missing():
    """Minimal documents get stable metadata defaults."""
    document = policy_document_from_mapping(
        {
            "version": "1",
            "policies": [
                {
                    "ref": "policy:no-condition",
                    "statements": [{"ref": "s", "effect": "allow"}],
                }
            ],
        }
    )
    assert document.metadata.name == "policy"
    assert document.metadata.description is None
    assert document.metadata.labels == ()
    assert document.policies[0].statements[0].condition is None


def test_load_policy_document_supports_json_toml_and_yaml(tmp_path):
    """Loader reads the three supported policy document formats."""
    json_path = tmp_path / "policy.json"
    toml_path = tmp_path / "policy.toml"
    yaml_path = tmp_path / "policy.yaml"

    json_path.write_text(json.dumps({"version": "json"}), encoding="UTF-8")
    toml_path.write_text('version = "toml"\n', encoding="UTF-8")
    yaml_path.write_text("version: yaml\n", encoding="UTF-8")

    assert load_policy_document(json_path).version == "json"
    assert load_policy_document(toml_path).version == "toml"
    assert load_policy_document(yaml_path).version == "yaml"


def test_load_policy_document_rejects_unsupported_extension(tmp_path):
    """Unsupported file extensions raise a load error."""
    path = tmp_path / "policy.txt"
    path.write_text("version: text", encoding="UTF-8")
    with pytest.raises(PolicyDocumentLoadError):
        load_policy_document(path)


def test_load_policy_document_wraps_parser_failures(tmp_path):
    """Malformed documents raise load errors."""
    path = tmp_path / "policy.json"
    path.write_text("{", encoding="UTF-8")
    with pytest.raises(PolicyDocumentLoadError):
        load_policy_document(path)


def test_load_policy_document_rejects_empty_yaml(tmp_path):
    """Empty YAML documents do not canonicalize as mappings."""
    path = tmp_path / "policy.yaml"
    path.write_text("", encoding="UTF-8")
    with pytest.raises(
        PolicyDocumentValidationError, match="document must be a mapping"
    ):
        load_policy_document(path)


def test_load_policy_document_rejects_non_string_mapping_keys(tmp_path):
    """All mapping keys must be strings."""
    path = tmp_path / "policy.yaml"
    path.write_text("1: invalid\n", encoding="UTF-8")
    with pytest.raises(
        PolicyDocumentValidationError, match="document contains non-string key"
    ):
        load_policy_document(path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"subjects": {"ref": "not-list"}}, "subjects must be a sequence"),
        ({"subjects": [{"ref": ""}]}, "subject.ref must be a non-empty string"),
        (
            {"subjects": [{"ref": "u", "claims": {"x": {}}}]},
            "claim must be a JSON scalar",
        ),
        (
            {
                "policies": [
                    {
                        "ref": "p",
                        "statements": [
                            {
                                "ref": "s",
                                "effect": "allow",
                                "condition": {
                                    "operator": "equals",
                                    "key": "k",
                                    "value": {},
                                },
                            }
                        ],
                    }
                ]
            },
            "condition.value must be scalar or sequence",
        ),
    ],
)
def test_policy_document_from_mapping_rejects_invalid_shapes(payload, message):
    """Invalid policy document structures fail loudly."""
    with pytest.raises(PolicyDocumentValidationError, match=message):
        policy_document_from_mapping(payload)
