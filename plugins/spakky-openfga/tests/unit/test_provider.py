from dataclasses import dataclass

from spakky.auth import (
    AuthCapability,
    AuthContext,
    AuthSubject,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthorizationRequest,
    RelationCheckRequest,
)
from spakky.plugins.openfga.client import (
    IOpenFgaCheckClient,
    OpenFgaCheckRequest,
    OpenFgaCheckResult,
)
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.constants import OPENFGA_AUTH_PROVIDER_ID
from spakky.plugins.openfga.error import OpenFgaProviderUnavailableError
from spakky.plugins.openfga.provider import (
    OpenFgaAuthProvider,
    openfga_auth_provider_contribution,
)


@dataclass(slots=True)
class RecordingCheckClient(IOpenFgaCheckClient):
    allowed: bool = True
    unavailable: bool = False
    requests: list[OpenFgaCheckRequest] | None = None

    def check(self, request: OpenFgaCheckRequest) -> OpenFgaCheckResult:
        if self.unavailable:
            raise OpenFgaProviderUnavailableError()
        if self.requests is None:
            self.requests = []
        self.requests.append(request)
        return OpenFgaCheckResult(allowed=self.allowed)


def _auth_context(
    subject_id: str = "alice",
    tenant: str | None = "tenant:ctx",
) -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id=subject_id),
        issuer="issuer:test",
        tenant=tenant,
    )


def _provider(
    client: IOpenFgaCheckClient,
    config: OpenFgaConfig | None = None,
) -> OpenFgaAuthProvider:
    return OpenFgaAuthProvider(
        client=client,
        config=OpenFgaConfig() if config is None else config,
    )


def test_relation_check_maps_principal_relation_resource_and_request_tenant() -> None:
    client = RecordingCheckClient()
    provider = _provider(client)

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(),
            relation="viewer",
            resource="document:doc-1",
            tenant="tenant:request",
        )
    )

    assert decision.state is AuthorizationDecisionState.ALLOW
    assert client.requests == [
        OpenFgaCheckRequest(
            user="user:alice",
            relation="viewer",
            object="tenant:request/document:doc-1",
        )
    ]


def test_policy_evaluation_maps_action_and_context_tenant_to_relation_check() -> None:
    client = RecordingCheckClient()
    provider = _provider(client)

    decision = provider.evaluate_policy(
        AuthorizationRequest(
            auth_context=_auth_context(subject_id="user:bob", tenant="tenant:acme"),
            resource="report:quarterly",
            action="reader",
        )
    )

    assert decision.state is AuthorizationDecisionState.ALLOW
    assert client.requests == [
        OpenFgaCheckRequest(
            user="user:bob",
            relation="reader",
            object="tenant:acme/report:quarterly",
        )
    ]


def test_relation_check_denies_when_openfga_denies() -> None:
    provider = _provider(RecordingCheckClient(allowed=False))

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(subject_id="user:alice", tenant=None),
            relation="editor",
            resource="document:doc-2",
        )
    )

    assert decision.state is AuthorizationDecisionState.DENY
    assert decision.reason_code is AuthorizationReasonCode.POLICY_DENIED


def test_provider_unavailable_maps_to_error_decision() -> None:
    provider = _provider(RecordingCheckClient(unavailable=True))

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(),
            relation="viewer",
            resource="document:doc-1",
        )
    )

    assert decision.state is AuthorizationDecisionState.ERROR
    assert (
        decision.reason_code
        is AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
    )


def test_configured_unavailable_maps_to_error_without_calling_client() -> None:
    client = RecordingCheckClient()
    provider = _provider(
        client=client,
        config=OpenFgaConfig().model_copy(update={"relation_check_available": False}),
    )

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(),
            relation="viewer",
            resource="document:doc-1",
        )
    )

    assert decision.state is AuthorizationDecisionState.ERROR
    assert (
        decision.reason_code
        is AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
    )
    assert client.requests is None


def test_blank_canonical_refs_map_to_internal_error_decision() -> None:
    client = RecordingCheckClient()
    provider = _provider(client)

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(),
            relation=" ",
            resource="document:doc-1",
        )
    )

    assert decision.state is AuthorizationDecisionState.ERROR
    assert decision.reason_code is AuthorizationReasonCode.INTERNAL_ERROR
    assert client.requests is None


def test_tenant_object_mapping_can_be_disabled() -> None:
    client = RecordingCheckClient()
    provider = _provider(
        client=client,
        config=OpenFgaConfig().model_copy(update={"include_tenant_in_object": False}),
    )

    decision = provider.check_relation(
        RelationCheckRequest(
            auth_context=_auth_context(),
            relation="viewer",
            resource="document:doc-1",
        )
    )

    assert decision.state is AuthorizationDecisionState.ALLOW
    assert client.requests == [
        OpenFgaCheckRequest(
            user="user:alice",
            relation="viewer",
            object="document:doc-1",
        )
    ]


def test_openfga_auth_provider_contribution_declares_auth_capabilities() -> None:
    contribution = openfga_auth_provider_contribution()

    assert contribution.provider_id == OPENFGA_AUTH_PROVIDER_ID
    assert contribution.supports(AuthCapability.RELATION_CHECK)
    assert contribution.supports(AuthCapability.POLICY_EVALUATION)
    assert not contribution.supports(AuthCapability.PASSWORD_HASH)
