"""OpenFGA-backed auth provider for relationship authorization."""

from typing import override

from spakky.auth import (
    AuthCapability,
    AuthProviderContribution,
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthorizationRequest,
    IAuthorizationPolicyEvaluator,
    IRelationChecker,
    RelationCheckRequest,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.openfga.client import (
    IOpenFgaCheckClient,
    OpenFgaCheckRequest,
    OpenFgaCheckResult,
)
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.constants import OPENFGA_AUTH_PROVIDER_ID
from spakky.plugins.openfga.error import (
    OpenFgaProviderUnavailableError,
    OpenFgaReferenceMappingError,
)


@Pod()
class OpenFgaAuthProvider(IRelationChecker, IAuthorizationPolicyEvaluator):
    """OpenFGA check-only provider for ReBAC authorization decisions."""

    _client: IOpenFgaCheckClient
    _config: OpenFgaConfig

    def __init__(
        self,
        client: IOpenFgaCheckClient,
        config: OpenFgaConfig,
    ) -> None:
        self._client = client
        self._config = config

    @override
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        """Check whether the subject has a relation to a resource."""
        return self._check(
            auth_context_subject_id=request.auth_context.subject.id,
            relation=request.relation,
            resource=request.resource,
            tenant=self._effective_tenant(request.tenant, request.auth_context.tenant),
        )

    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        """Map resource/action policy evaluation to an OpenFGA relation check."""
        return self._check(
            auth_context_subject_id=request.auth_context.subject.id,
            relation=request.action,
            resource=request.resource,
            tenant=self._effective_tenant(request.tenant, request.auth_context.tenant),
        )

    def _check(
        self,
        *,
        auth_context_subject_id: str,
        relation: str,
        resource: str,
        tenant: str | None,
    ) -> AuthorizationDecision:
        if not self._config.relation_check_available:
            return self._unavailable_decision()
        try:
            result = self._client.check(
                OpenFgaCheckRequest(
                    user=self._openfga_user(auth_context_subject_id),
                    relation=self._required_ref(relation),
                    object=self._openfga_object(resource, tenant),
                )
            )
        except OpenFgaProviderUnavailableError:
            return self._unavailable_decision()
        except OpenFgaReferenceMappingError:
            return AuthorizationDecision.error(
                AuthorizationReasonCode.INTERNAL_ERROR,
                reason="OpenFGA canonical reference mapping failed",
            )
        return self._decision_from_result(result)

    def _openfga_user(self, subject_id: str) -> str:
        principal = self._required_ref(subject_id)
        if ":" in principal:
            return principal
        return f"{self._required_ref(self._config.principal_type)}:{principal}"

    def _openfga_object(self, resource: str, tenant: str | None) -> str:
        canonical_resource = self._required_ref(resource)
        if tenant is None or not self._config.include_tenant_in_object:
            return canonical_resource
        canonical_tenant = self._required_ref(tenant)
        separator = self._required_ref(self._config.tenant_separator)
        return f"{canonical_tenant}{separator}{canonical_resource}"

    def _effective_tenant(
        self,
        request_tenant: str | None,
        context_tenant: str | None,
    ) -> str | None:
        if request_tenant is not None:
            return request_tenant
        return context_tenant

    def _required_ref(self, value: str) -> str:
        if value.strip() == "":
            raise OpenFgaReferenceMappingError()
        return value

    def _decision_from_result(
        self,
        result: OpenFgaCheckResult,
    ) -> AuthorizationDecision:
        if result.allowed:
            return AuthorizationDecision.allow()
        return AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)

    def _unavailable_decision(self) -> AuthorizationDecision:
        return AuthorizationDecision.error(
            AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE,
            reason="OpenFGA relation check provider unavailable",
        )


@Pod(name="spakky_openfga_auth_provider_contribution")
def openfga_auth_provider_contribution() -> AuthProviderContribution:
    """Return the auth capabilities contributed by spakky-openfga."""
    return AuthProviderContribution(
        provider_id=OPENFGA_AUTH_PROVIDER_ID,
        capabilities=frozenset(
            {
                AuthCapability.POLICY_EVALUATION,
                AuthCapability.RELATION_CHECK,
            }
        ),
    )
