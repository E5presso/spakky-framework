"""Deterministic sensitive-data contracts for agent boundaries."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from spakky.agent.error import AgentDefinitionError
from spakky.agent.types import JsonObject, JsonValue

REDACTED_VALUE = "[REDACTED]"
SECRET_VALUE = "[SECRET]"


class DataSensitivity(StrEnum):
    """Canonical sensitivity classes carried by descriptors."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    SECRET = "secret"


class PII(StrEnum):
    """PII categories that can be declared with typing.Annotated."""

    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    ACCOUNT_ID = "account_id"
    IDENTIFIER = "identifier"
    LOCATION = "location"


class MaskingPolicy(StrEnum):
    """Deterministic text masking strategies for sensitive values."""

    REDACT = "redact"
    LAST_FOUR = "last_four"
    FIRST_LAST = "first_last"
    HASH = "hash"


class RedactionPolicy(StrEnum):
    """Boundary action used when a value must not be exposed."""

    REDACT = "redact"
    DROP = "drop"
    REFERENCE_ONLY = "reference_only"


@dataclass(frozen=True, slots=True)
class ContextExposurePolicy:
    """Policy for LLM-facing context and schema metadata exposure."""

    include_pii_values: bool = False
    include_sensitive_values: bool = False
    include_sensitive_schema_metadata: bool = False
    include_sensitive_context_metadata: bool = False

    def can_expose_value(self, field: "SensitiveField | SecretField") -> bool:
        """Return whether a sensitive value may cross the model boundary."""
        if isinstance(field, SecretField):
            return False
        if field.sensitivity == DataSensitivity.PII:
            return self.include_pii_values
        if field.sensitivity in (DataSensitivity.CONFIDENTIAL, DataSensitivity.SECRET):
            return self.include_sensitive_values
        return True


@dataclass(frozen=True, slots=True)
class EvidenceExposurePolicy:
    """Policy for evidence payload exposure before append-only capture."""

    include_pii_values: bool = False
    include_sensitive_values: bool = False
    include_sensitive_metadata: bool = True

    def can_expose_value(self, field: "SensitiveField | SecretField") -> bool:
        """Return whether a sensitive value may be stored in evidence payloads."""
        if isinstance(field, SecretField):
            return False
        if field.sensitivity == DataSensitivity.PII:
            return self.include_pii_values
        if field.sensitivity in (DataSensitivity.CONFIDENTIAL, DataSensitivity.SECRET):
            return self.include_sensitive_values
        return True


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """Reference to a credential outside LLM-facing context."""

    id: str
    provider: str | None = None

    def __post_init__(self) -> None:
        """Reject blank credential references."""
        _require_non_blank(self.id, "Credential reference id")
        if self.provider is not None:
            _require_non_blank(self.provider, "Credential provider")


@dataclass(frozen=True, slots=True)
class SecretRef:
    """Opaque reference to a secret value stored outside model context."""

    id: str
    credential: CredentialRef | None = None

    def __post_init__(self) -> None:
        """Reject blank secret references."""
        _require_non_blank(self.id, "Secret reference id")


@dataclass(frozen=True, slots=True)
class SensitiveField:
    """typing.Annotated metadata for deterministic sensitive-field handling."""

    category: PII | DataSensitivity
    masking: MaskingPolicy = MaskingPolicy.REDACT
    redaction: RedactionPolicy = RedactionPolicy.REDACT
    label: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject blank sensitive field labels."""
        if self.label is not None:
            _require_non_blank(self.label, "Sensitive field label")

    @property
    def sensitivity(self) -> DataSensitivity:
        """Return the normalized sensitivity class."""
        if isinstance(self.category, PII):
            return DataSensitivity.PII
        return self.category

    @property
    def category_name(self) -> str:
        """Return the stable public category name."""
        return self.category.value

    def guard_text(self, value: str) -> str:
        """Return deterministic model/evidence-safe text for this field."""
        return _mask_text(value, self.masking, self.category_name)

    def to_metadata(self) -> JsonObject:
        """Serialize marker metadata without including the sensitive value."""
        payload: dict[str, JsonValue] = {
            "kind": "sensitive",
            "category": self.category_name,
            "sensitivity": self.sensitivity.value,
            "masking": self.masking.value,
            "redaction": self.redaction.value,
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True, slots=True)
class SecretField:
    """typing.Annotated metadata for values that must never be model text."""

    redaction: RedactionPolicy = RedactionPolicy.REFERENCE_ONLY
    label: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject blank secret field labels."""
        if self.label is not None:
            _require_non_blank(self.label, "Secret field label")

    @property
    def sensitivity(self) -> DataSensitivity:
        """Return the normalized sensitivity class."""
        return DataSensitivity.SECRET

    def guard_text(self, value: str) -> str:
        """Return deterministic replacement text for a secret value."""
        return SECRET_VALUE

    def to_metadata(self) -> JsonObject:
        """Serialize marker metadata without including the secret value."""
        payload: dict[str, JsonValue] = {
            "kind": "secret",
            "sensitivity": DataSensitivity.SECRET.value,
            "redaction": self.redaction.value,
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True, slots=True)
class SensitiveFieldDescriptor:
    """Path-bound sensitive metadata extracted from Annotated types."""

    path: tuple[str, ...]
    field: SensitiveField | SecretField

    def to_metadata(self) -> JsonObject:
        """Serialize descriptor metadata without leaking the field value."""
        return {
            "path": list(self.path),
            "field": self.field.to_metadata(),
        }


def guard_json_value(
    value: JsonValue,
    sensitive_fields: Sequence[SensitiveFieldDescriptor],
    policy: ContextExposurePolicy | EvidenceExposurePolicy,
) -> JsonValue:
    """Redact JSON-compatible values according to path-bound descriptors."""
    result = value
    for descriptor in sensitive_fields:
        result = _guard_json_path(result, descriptor.path, descriptor.field, policy)
    return result


def schema_with_sensitive_metadata(
    schema: Mapping[str, JsonValue],
    sensitive_fields: Sequence[SensitiveFieldDescriptor],
    policy: ContextExposurePolicy,
) -> JsonObject:
    """Return a JSON schema copy with policy-approved sensitivity extensions."""
    if not policy.include_sensitive_schema_metadata or not sensitive_fields:
        return schema
    result = _copy_json_object(schema)
    for descriptor in sensitive_fields:
        _attach_schema_extension(result, descriptor.path, descriptor.to_metadata())
    return result


def _guard_json_path(
    value: JsonValue,
    path: Sequence[str],
    field: SensitiveField | SecretField,
    policy: ContextExposurePolicy | EvidenceExposurePolicy,
) -> JsonValue:
    if not path:
        return _guard_scalar(value, field, policy)
    if not isinstance(value, Mapping):
        return value
    key = path[0]
    if key not in value:
        return value
    result: dict[str, JsonValue] = dict(value)
    guarded = _guard_json_path(value[key], path[1:], field, policy)
    if field.redaction == RedactionPolicy.DROP and not policy.can_expose_value(field):
        result.pop(key)
    else:
        result[key] = guarded
    return result


def _guard_scalar(
    value: JsonValue,
    field: SensitiveField | SecretField,
    policy: ContextExposurePolicy | EvidenceExposurePolicy,
) -> JsonValue:
    if policy.can_expose_value(field):
        return value
    if isinstance(value, str):
        return field.guard_text(value)
    if field.redaction == RedactionPolicy.DROP:
        return None
    return field.guard_text(str(value))


def _copy_json_object(schema: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in schema.items():
        if isinstance(value, Mapping):
            result[key] = _copy_json_object(value)
        elif isinstance(value, Sequence) and not isinstance(value, str):
            result[key] = [_copy_json_value(item) for item in value]
        else:
            result[key] = value
    return result


def _copy_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return _copy_json_object(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_copy_json_value(item) for item in value]
    return value


def _attach_schema_extension(
    schema: dict[str, JsonValue],
    path: Sequence[str],
    metadata: JsonObject,
) -> None:
    target = schema
    for part in path:
        properties = target.get("properties")
        if not isinstance(properties, Mapping):
            return
        candidate = properties.get(part)
        if not isinstance(candidate, Mapping):
            return
        target = dict(candidate)
        copied_properties = dict(properties)
        copied_properties[part] = target
        schema["properties"] = copied_properties
        schema = target
    existing = target.get("x-spakky-sensitive")
    if isinstance(existing, Sequence) and not isinstance(existing, str):
        target["x-spakky-sensitive"] = [*existing, metadata]
    else:
        target["x-spakky-sensitive"] = [metadata]


def _mask_text(value: str, policy: MaskingPolicy, category: str) -> str:
    if policy == MaskingPolicy.LAST_FOUR:
        return f"***{value[-4:]}" if len(value) > 4 else REDACTED_VALUE
    if policy == MaskingPolicy.FIRST_LAST:
        return f"{value[0]}***{value[-1]}" if len(value) > 1 else REDACTED_VALUE
    if policy == MaskingPolicy.HASH:
        digest = sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"[HASHED:{category}:{digest}]"
    return REDACTED_VALUE


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")
