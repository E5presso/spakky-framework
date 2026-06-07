"""Canonical policy document and evaluation evidence model."""

from dataclasses import dataclass
from enum import StrEnum


type JsonScalar = str | int | float | bool | None
type ClaimValue = JsonScalar
type PolicyRef = str


class PolicyEffect(StrEnum):
    """Effects supported by policy statements."""

    ALLOW = "allow"
    DENY = "deny"


class ConditionOperator(StrEnum):
    """Operators supported by atomic conditions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    CONTAINS = "contains"
    EXISTS = "exists"


class ConditionComposition(StrEnum):
    """Boolean composition forms for policy conditions."""

    ALL = "all"
    ANY = "any"
    NOT = "not"


class PolicyEvidenceKind(StrEnum):
    """Machine-readable evidence categories emitted during evaluation."""

    STATEMENT_MATCHED = "statement_matched"
    STATEMENT_SKIPPED = "statement_skipped"
    CONDITION_MATCHED = "condition_matched"
    CONDITION_FAILED = "condition_failed"
    DEFAULT_DENY = "default_deny"


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyMetadata:
    """Human and operational metadata for a policy document."""

    name: str
    description: str | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicySubject:
    """Canonical subject binding declared in a policy document."""

    ref: PolicyRef
    roles: tuple[PolicyRef, ...] = ()
    scopes: tuple[PolicyRef, ...] = ()
    permissions: tuple[PolicyRef, ...] = ()
    claims: tuple[tuple[str, ClaimValue], ...] = ()
    tenant: PolicyRef | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyResource:
    """Canonical resource binding."""

    ref: PolicyRef
    tenant: PolicyRef | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyAction:
    """Canonical action binding."""

    ref: PolicyRef


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyPermission:
    """Named permission expanded into resource/action requirements."""

    ref: PolicyRef
    resources: tuple[PolicyRef, ...] = ()
    actions: tuple[PolicyRef, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyRole:
    """Named role expanded into permission requirements."""

    ref: PolicyRef
    permissions: tuple[PolicyRef, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyScope:
    """Named scope expanded into permission requirements."""

    ref: PolicyRef
    permissions: tuple[PolicyRef, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyCondition:
    """Atomic or composite condition."""

    ref: PolicyRef | None = None
    operator: ConditionOperator | None = None
    key: str | None = None
    value: ClaimValue | tuple[ClaimValue, ...] = None
    composition: ConditionComposition | None = None
    children: tuple["PolicyCondition", ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyStatement:
    """Single allow or deny statement in a named policy."""

    ref: PolicyRef
    effect: PolicyEffect
    subjects: tuple[PolicyRef, ...] = ()
    roles: tuple[PolicyRef, ...] = ()
    scopes: tuple[PolicyRef, ...] = ()
    permissions: tuple[PolicyRef, ...] = ()
    resources: tuple[PolicyRef, ...] = ()
    actions: tuple[PolicyRef, ...] = ()
    tenants: tuple[PolicyRef, ...] = ()
    condition: PolicyCondition | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NamedPolicy:
    """Named policy composed from statements with OR/ANY semantics."""

    ref: PolicyRef
    statements: tuple[PolicyStatement, ...]
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyDocument:
    """Typed canonical Spakky policy document."""

    version: str
    metadata: PolicyMetadata
    subjects: tuple[PolicySubject, ...] = ()
    resources: tuple[PolicyResource, ...] = ()
    actions: tuple[PolicyAction, ...] = ()
    permissions: tuple[PolicyPermission, ...] = ()
    roles: tuple[PolicyRole, ...] = ()
    scopes: tuple[PolicyScope, ...] = ()
    policies: tuple[NamedPolicy, ...] = ()
    conditions: tuple[PolicyCondition, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyEvaluationEvidence:
    """Explainable evidence emitted by policy evaluation."""

    kind: PolicyEvidenceKind
    policy: PolicyRef | None = None
    statement: PolicyRef | None = None
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyEvaluationResult:
    """Policy evaluator result with explainable evidence."""

    allowed: bool
    effect: PolicyEffect | None
    evidence: tuple[PolicyEvaluationEvidence, ...]
