"""YAML, TOML, and JSON policy document loading."""

from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import tomllib

import yaml

from spakky.plugins.policy.error import (
    PolicyDocumentLoadError,
    PolicyDocumentValidationError,
)
from spakky.plugins.policy.model import (
    ClaimValue,
    ConditionComposition,
    ConditionOperator,
    NamedPolicy,
    PolicyAction,
    PolicyCondition,
    PolicyDocument,
    PolicyEffect,
    PolicyMetadata,
    PolicyPermission,
    PolicyResource,
    PolicyRole,
    PolicyScope,
    PolicyStatement,
    PolicySubject,
)

RawMapping = Mapping[str, object]


def load_policy_document(path: str | Path) -> PolicyDocument:
    """Load a policy document from YAML, TOML, or JSON."""
    policy_path = Path(path)
    suffix = policy_path.suffix.lower()
    try:
        if suffix == ".json":
            loaded = json.loads(policy_path.read_text(encoding="UTF-8"))
        elif suffix == ".toml":
            loaded = tomllib.loads(policy_path.read_text(encoding="UTF-8"))
        elif suffix in {".yaml", ".yml"}:
            loaded = yaml.safe_load(policy_path.read_text(encoding="UTF-8"))
        else:
            raise PolicyDocumentLoadError("unsupported policy document extension")
    except PolicyDocumentLoadError:
        raise
    except Exception as exc:
        raise PolicyDocumentLoadError("policy document could not be loaded") from exc
    return policy_document_from_mapping(_mapping(loaded, "document"))


def policy_document_from_mapping(payload: RawMapping) -> PolicyDocument:
    """Canonicalize an in-memory policy document mapping."""
    payload = _mapping(payload, "document")
    metadata = _mapping(payload.get("metadata", {"name": "policy"}), "metadata")
    return PolicyDocument(
        version=_string(payload.get("version", "1"), "version"),
        metadata=PolicyMetadata(
            name=_string(metadata.get("name", "policy"), "metadata.name"),
            description=_optional_string(
                metadata.get("description"), "metadata.description"
            ),
            labels=_string_tuple(metadata.get("labels", ()), "metadata.labels"),
        ),
        subjects=tuple(
            _subject(item)
            for item in _sequence(payload.get("subjects", ()), "subjects")
        ),
        resources=tuple(
            _resource(item)
            for item in _sequence(payload.get("resources", ()), "resources")
        ),
        actions=tuple(
            _action(item) for item in _sequence(payload.get("actions", ()), "actions")
        ),
        permissions=tuple(
            _permission(item)
            for item in _sequence(payload.get("permissions", ()), "permissions")
        ),
        roles=tuple(
            _role(item) for item in _sequence(payload.get("roles", ()), "roles")
        ),
        scopes=tuple(
            _scope(item) for item in _sequence(payload.get("scopes", ()), "scopes")
        ),
        policies=tuple(
            _policy(item) for item in _sequence(payload.get("policies", ()), "policies")
        ),
        conditions=tuple(
            _condition(item)
            for item in _sequence(payload.get("conditions", ()), "conditions")
        ),
    )


def _subject(item: object) -> PolicySubject:
    payload = _mapping(item, "subject")
    return PolicySubject(
        ref=_string(payload.get("ref"), "subject.ref"),
        roles=_string_tuple(payload.get("roles", ()), "subject.roles"),
        scopes=_string_tuple(payload.get("scopes", ()), "subject.scopes"),
        permissions=_string_tuple(
            payload.get("permissions", ()), "subject.permissions"
        ),
        claims=_claims(payload.get("claims", {})),
        tenant=_optional_string(payload.get("tenant"), "subject.tenant"),
    )


def _resource(item: object) -> PolicyResource:
    payload = _mapping(item, "resource")
    return PolicyResource(
        ref=_string(payload.get("ref"), "resource.ref"),
        tenant=_optional_string(payload.get("tenant"), "resource.tenant"),
    )


def _action(item: object) -> PolicyAction:
    payload = _mapping(item, "action")
    return PolicyAction(ref=_string(payload.get("ref"), "action.ref"))


def _permission(item: object) -> PolicyPermission:
    payload = _mapping(item, "permission")
    return PolicyPermission(
        ref=_string(payload.get("ref"), "permission.ref"),
        resources=_string_tuple(payload.get("resources", ()), "permission.resources"),
        actions=_string_tuple(payload.get("actions", ()), "permission.actions"),
    )


def _role(item: object) -> PolicyRole:
    payload = _mapping(item, "role")
    return PolicyRole(
        ref=_string(payload.get("ref"), "role.ref"),
        permissions=_string_tuple(payload.get("permissions", ()), "role.permissions"),
    )


def _scope(item: object) -> PolicyScope:
    payload = _mapping(item, "scope")
    return PolicyScope(
        ref=_string(payload.get("ref"), "scope.ref"),
        permissions=_string_tuple(payload.get("permissions", ()), "scope.permissions"),
    )


def _policy(item: object) -> NamedPolicy:
    payload = _mapping(item, "policy")
    return NamedPolicy(
        ref=_string(payload.get("ref"), "policy.ref"),
        description=_optional_string(payload.get("description"), "policy.description"),
        statements=tuple(
            _statement(statement)
            for statement in _sequence(
                payload.get("statements", ()), "policy.statements"
            )
        ),
    )


def _statement(item: object) -> PolicyStatement:
    payload = _mapping(item, "statement")
    return PolicyStatement(
        ref=_string(payload.get("ref"), "statement.ref"),
        effect=PolicyEffect(_string(payload.get("effect"), "statement.effect")),
        subjects=_string_tuple(payload.get("subjects", ()), "statement.subjects"),
        roles=_string_tuple(payload.get("roles", ()), "statement.roles"),
        scopes=_string_tuple(payload.get("scopes", ()), "statement.scopes"),
        permissions=_string_tuple(
            payload.get("permissions", ()), "statement.permissions"
        ),
        resources=_string_tuple(payload.get("resources", ()), "statement.resources"),
        actions=_string_tuple(payload.get("actions", ()), "statement.actions"),
        tenants=_string_tuple(payload.get("tenants", ()), "statement.tenants"),
        condition=_optional_condition(payload.get("condition")),
    )


def _optional_condition(item: object) -> PolicyCondition | None:
    if item is None:
        return None
    return _condition(item)


def _condition(item: object) -> PolicyCondition:
    if isinstance(item, str):
        return PolicyCondition(ref=item)
    payload = _mapping(item, "condition")
    composition = _optional_composition(payload)
    if composition is not None:
        return PolicyCondition(
            ref=_optional_string(payload.get("ref"), "condition.ref"),
            composition=composition,
            children=_condition_children(payload, composition),
        )
    return PolicyCondition(
        ref=_optional_string(payload.get("ref"), "condition.ref"),
        operator=ConditionOperator(
            _string(payload.get("operator"), "condition.operator")
        ),
        key=_string(payload.get("key"), "condition.key"),
        value=_condition_value(payload.get("value")),
    )


def _optional_composition(payload: RawMapping) -> ConditionComposition | None:
    for key in ("all", "any", "not"):
        if key in payload:
            return ConditionComposition(key)
    return None


def _condition_children(
    payload: RawMapping,
    composition: ConditionComposition,
) -> tuple[PolicyCondition, ...]:
    child_value = payload.get(composition.value)
    if composition is ConditionComposition.NOT:
        return (_condition(child_value),)
    return tuple(
        _condition(item) for item in _sequence(child_value, "condition.children")
    )


def _condition_value(value: object) -> ClaimValue | tuple[ClaimValue, ...]:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_scalar(item, "condition.value") for item in value)
    raise PolicyDocumentValidationError("condition.value must be scalar or sequence")


def _claims(value: object) -> tuple[tuple[str, ClaimValue], ...]:
    payload = _mapping(value, "claims")
    return tuple((key, _scalar(item, "claim")) for key, item in sorted(payload.items()))


def _mapping(value: object, label: str) -> RawMapping:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PolicyDocumentValidationError(f"{label} contains non-string key")
            result[key] = item
        return result
    raise PolicyDocumentValidationError(f"{label} must be a mapping")


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    raise PolicyDocumentValidationError(f"{label} must be a sequence")


def _string(value: object, label: str) -> str:
    if isinstance(value, str) and value != "":
        return value
    raise PolicyDocumentValidationError(f"{label} must be a non-empty string")


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(_string(item, label) for item in _sequence(value, label))


def _scalar(value: object, label: str) -> ClaimValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise PolicyDocumentValidationError(f"{label} must be a JSON scalar")
