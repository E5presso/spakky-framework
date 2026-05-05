"""Tests for deterministic sensitive-data guard contracts."""

import pytest

from spakky.agent import (
    AgentDefinitionError,
    ContextExposurePolicy,
    CredentialRef,
    DataSensitivity,
    EvidenceExposurePolicy,
    MaskingPolicy,
    PII,
    RedactionPolicy,
    SecretField,
    SecretRef,
    SensitiveField,
    SensitiveFieldDescriptor,
)
from spakky.agent.safety import (
    REDACTED_VALUE,
    SECRET_VALUE,
    guard_json_value,
    schema_with_sensitive_metadata,
)


def test_sensitive_policy_expect_handles_public_confidential_pii_and_secret() -> None:
    """exposure policy는 sensitivity class별로 value 노출 여부를 결정한다."""
    public = SensitiveField(DataSensitivity.PUBLIC)
    confidential = SensitiveField(DataSensitivity.CONFIDENTIAL)
    pii = SensitiveField(PII.EMAIL)
    secret = SecretField()

    context_policy = ContextExposurePolicy(
        include_pii_values=True,
        include_sensitive_values=True,
    )
    evidence_policy = EvidenceExposurePolicy(
        include_pii_values=True,
        include_sensitive_values=True,
    )

    assert ContextExposurePolicy().can_expose_value(public) is True
    assert ContextExposurePolicy().can_expose_value(confidential) is False
    assert ContextExposurePolicy().can_expose_value(pii) is False
    assert context_policy.can_expose_value(confidential) is True
    assert context_policy.can_expose_value(pii) is True
    assert context_policy.can_expose_value(secret) is False
    assert EvidenceExposurePolicy().can_expose_value(confidential) is False
    assert EvidenceExposurePolicy().can_expose_value(pii) is False
    assert EvidenceExposurePolicy().can_expose_value(public) is True
    assert evidence_policy.can_expose_value(confidential) is True
    assert evidence_policy.can_expose_value(pii) is True
    assert evidence_policy.can_expose_value(secret) is False


def test_sensitive_refs_and_markers_expect_validate_blank_labels() -> None:
    """credential/secret refs와 marker label은 blank 값을 거부한다."""
    assert SecretRef("secret-1", credential=CredentialRef("credential-1")).id == (
        "secret-1"
    )
    assert SensitiveField(
        PII.NAME,
        label="customer-name",
        metadata={"source": "crm"},
    ).to_metadata() == {
        "kind": "sensitive",
        "category": "name",
        "sensitivity": "pii",
        "masking": "redact",
        "redaction": "redact",
        "label": "customer-name",
        "metadata": {"source": "crm"},
    }
    assert SecretField(
        label="api-token",
        metadata={"vault": "primary"},
    ).to_metadata() == {
        "kind": "secret",
        "sensitivity": "secret",
        "redaction": "reference_only",
        "label": "api-token",
        "metadata": {"vault": "primary"},
    }
    assert SecretField().sensitivity == DataSensitivity.SECRET
    assert SecretField().guard_text("raw") == SECRET_VALUE

    with pytest.raises(AgentDefinitionError):
        CredentialRef(" ")
    with pytest.raises(AgentDefinitionError):
        CredentialRef("credential-1", provider=" ")
    with pytest.raises(AgentDefinitionError):
        SecretRef(" ")
    with pytest.raises(AgentDefinitionError):
        SensitiveField(PII.NAME, label=" ")
    with pytest.raises(AgentDefinitionError):
        SecretField(label=" ")


def test_guard_json_value_expect_redacts_masks_drops_and_preserves_missing_paths() -> (
    None
):
    """JSON guard는 path descriptor를 따라 deterministic replacement를 적용한다."""
    payload = {
        "email": "owner@example.com",
        "name": "Ada",
        "token": "sk-live-1234",
        "missing": "kept",
        "nested": {"account": "123456789"},
    }
    guarded = guard_json_value(
        payload,
        (
            SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL)),
            SensitiveFieldDescriptor(
                ("name",),
                SensitiveField(PII.NAME, masking=MaskingPolicy.FIRST_LAST),
            ),
            SensitiveFieldDescriptor(
                ("token",),
                SensitiveField(
                    DataSensitivity.CONFIDENTIAL,
                    redaction=RedactionPolicy.DROP,
                ),
            ),
            SensitiveFieldDescriptor(
                ("nested", "account"),
                SensitiveField(PII.ACCOUNT_ID, masking=MaskingPolicy.LAST_FOUR),
            ),
            SensitiveFieldDescriptor(("absent",), SensitiveField(PII.IDENTIFIER)),
        ),
        EvidenceExposurePolicy(),
    )

    assert guarded == {
        "email": REDACTED_VALUE,
        "name": "A***a",
        "missing": "kept",
        "nested": {"account": "***6789"},
    }
    assert (
        guard_json_value(
            "raw",
            (SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL)),),
            EvidenceExposurePolicy(),
        )
        == "raw"
    )
    assert (
        guard_json_value(
            123,
            (SensitiveFieldDescriptor((), SensitiveField(PII.IDENTIFIER)),),
            EvidenceExposurePolicy(),
        )
        == REDACTED_VALUE
    )
    assert (
        guard_json_value(
            123,
            (
                SensitiveFieldDescriptor(
                    (),
                    SensitiveField(PII.IDENTIFIER, redaction=RedactionPolicy.DROP),
                ),
            ),
            EvidenceExposurePolicy(),
        )
        is None
    )
    assert guard_json_value(
        {"email": "owner@example.com"},
        (SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL)),),
        EvidenceExposurePolicy(include_pii_values=True),
    ) == {"email": "owner@example.com"}


def test_schema_extension_expect_copies_nested_lists_and_handles_absent_path() -> None:
    """schema extension은 원본 schema를 바꾸지 않고 가능한 path에만 붙는다."""
    schema = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "examples": [["owner@example.com"]],
                    },
                },
            },
        },
    }
    fields = (
        SensitiveFieldDescriptor(("profile", "email"), SensitiveField(PII.EMAIL)),
        SensitiveFieldDescriptor(("profile", "missing"), SensitiveField(PII.NAME)),
    )

    hidden = schema_with_sensitive_metadata(schema, fields, ContextExposurePolicy())
    visible = schema_with_sensitive_metadata(
        schema,
        fields,
        ContextExposurePolicy(include_sensitive_schema_metadata=True),
    )
    visible_twice = schema_with_sensitive_metadata(
        visible,
        fields[:1],
        ContextExposurePolicy(include_sensitive_schema_metadata=True),
    )
    expected_visible = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "examples": [["owner@example.com"]],
                        "x-spakky-sensitive": [
                            {
                                "path": ["profile", "email"],
                                "field": {
                                    "kind": "sensitive",
                                    "category": "email",
                                    "sensitivity": "pii",
                                    "masking": "redact",
                                    "redaction": "redact",
                                },
                            },
                        ],
                    },
                },
            },
        },
    }
    expected_visible_twice = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "examples": [["owner@example.com"]],
                        "x-spakky-sensitive": [
                            {
                                "path": ["profile", "email"],
                                "field": {
                                    "kind": "sensitive",
                                    "category": "email",
                                    "sensitivity": "pii",
                                    "masking": "redact",
                                    "redaction": "redact",
                                },
                            },
                            {
                                "path": ["profile", "email"],
                                "field": {
                                    "kind": "sensitive",
                                    "category": "email",
                                    "sensitivity": "pii",
                                    "masking": "redact",
                                    "redaction": "redact",
                                },
                            },
                        ],
                    },
                },
            },
        },
    }

    assert hidden is schema
    assert schema == {
        "type": "object",
        "properties": {
            "profile": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "examples": [["owner@example.com"]],
                    },
                },
            },
        },
    }
    assert visible == expected_visible
    assert visible_twice == expected_visible_twice
    assert schema_with_sensitive_metadata(
        {"type": "object"},
        (SensitiveFieldDescriptor(("missing",), SensitiveField(PII.NAME)),),
        ContextExposurePolicy(include_sensitive_schema_metadata=True),
    ) == {"type": "object"}


def test_masking_policy_expect_supports_last_four_first_last_hash_and_redact() -> None:
    """masking policy는 detector 없이 입력 문자열만으로 deterministic하다."""
    short_last_four = SensitiveField(PII.PHONE, masking=MaskingPolicy.LAST_FOUR)
    first_last_short = SensitiveField(PII.NAME, masking=MaskingPolicy.FIRST_LAST)
    hashed = SensitiveField(PII.EMAIL, masking=MaskingPolicy.HASH)
    redacted = SensitiveField(PII.ADDRESS)

    assert short_last_four.guard_text("123") == REDACTED_VALUE
    assert first_last_short.guard_text("A") == REDACTED_VALUE
    assert hashed.guard_text("owner@example.com").startswith("[HASHED:email:")
    assert redacted.guard_text("1 Main Street") == REDACTED_VALUE
