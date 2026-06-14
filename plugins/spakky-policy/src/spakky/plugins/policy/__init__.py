"""spakky-policy plugin."""

from spakky.core.application.plugin import Plugin
from spakky.plugins.policy.auth_provider import (
    POLICY_AUTH_PROVIDER_ID,
    SpakkyPolicyAuthProvider,
    policy_auth_provider_contribution,
    spakky_policy_document,
)
from spakky.plugins.policy.config import SpakkyPolicyConfig
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

PLUGIN_NAME = Plugin(name="spakky-policy")

__all__ = [
    "PLUGIN_NAME",
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
    "SpakkyPolicyConfig",
    "SpakkyPolicyAuthProvider",
    "load_policy_document",
    "policy_auth_provider_contribution",
    "policy_document_from_mapping",
    "spakky_policy_document",
]
