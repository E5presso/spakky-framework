"""spakky-policy plugin."""

from spakky.plugins.policy.auth_provider import (
    POLICY_AUTH_PROVIDER_ID,
    SpakkyPolicyAuthProvider,
    policy_auth_provider_contribution,
)
from spakky.plugins.policy.evaluator import (
    PolicyDocumentEvaluator,
    PolicyEvaluationInput,
)
from spakky.plugins.policy.loader import (
    load_policy_document,
    policy_document_from_mapping,
)
from spakky.plugins.policy.model import (
    ConditionComposition,
    ConditionOperator,
    NamedPolicy,
    PolicyAction,
    PolicyCondition,
    PolicyDocument,
    PolicyEffect,
    PolicyEvaluationEvidence,
    PolicyEvaluationResult,
    PolicyEvidenceKind,
    PolicyMetadata,
    PolicyPermission,
    PolicyResource,
    PolicyRole,
    PolicyScope,
    PolicyStatement,
    PolicySubject,
)

__all__ = [
    "POLICY_AUTH_PROVIDER_ID",
    "ConditionComposition",
    "ConditionOperator",
    "NamedPolicy",
    "PolicyAction",
    "PolicyCondition",
    "PolicyDocument",
    "PolicyDocumentEvaluator",
    "PolicyEffect",
    "PolicyEvaluationEvidence",
    "PolicyEvaluationInput",
    "PolicyEvaluationResult",
    "PolicyEvidenceKind",
    "PolicyMetadata",
    "PolicyPermission",
    "PolicyResource",
    "PolicyRole",
    "PolicyScope",
    "PolicyStatement",
    "PolicySubject",
    "SpakkyPolicyAuthProvider",
    "load_policy_document",
    "policy_auth_provider_contribution",
    "policy_document_from_mapping",
]
