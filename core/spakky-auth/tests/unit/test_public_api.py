from datetime import UTC, datetime
from base64 import urlsafe_b64decode
import json

import pytest

from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION,
    AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY,
    DEFAULT_AUTH_CLOCK_SKEW_SECONDS,
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    PLUGIN_NAME,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AbstractSpakkyAuthError,
    AuthCapability,
    AuthClaim,
    AuthContext,
    AuthContextNotFoundError,
    AuthRequirement,
    AuthRequirementDeniedError,
    AuthRequirementKind,
    AuthRequirementProviderUnavailableError,
    AuthContextSnapshot,
    AuthContextSnapshotError,
    AuthContextSnapshotSignature,
    AuthCapabilityStartupValidationService,
    AuthSnapshotPropagationConfig,
    AuthStartupCapabilityDiagnostic,
    AuthStartupCapabilityValidationError,
    AuthStartupContainerUnavailableError,
    AuthSubject,
    AuthVerificationProviderUnavailableError,
    AuthenticationError,
    AsyncAuthorizationAspect,
    AuthorizationDecision,
    AuthorizationAspect,
    AuthorizationDecisionState,
    AuthorizationError,
    AuthorizationReasonCode,
    ConflictingAuthMetadataError,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    InvalidAuthContextValueError,
    ProtectedRequirement,
    PublicAccess,
    get_effective_auth_metadata,
    has_auth_boundary_metadata,
    protected,
    public_access,
    require_auth_context,
    require_permission,
    require_policy,
    require_relation,
    require_role,
    require_scope,
    store_auth_context,
)
from spakky.auth.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_plugin_name_identifies_auth_package() -> None:
    assert PLUGIN_NAME.name == "spakky-auth"


def test_initialize_registers_authorization_aspects() -> None:
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    pod_types = {pod.type_ for pod in app.container.pods.values()}
    assert AuthCapabilityStartupValidationService in pod_types
    assert AuthorizationAspect in pod_types
    assert AsyncAuthorizationAspect in pod_types


def test_auth_constants_define_context_and_snapshot_contract_keys() -> None:
    assert AUTH_CONTEXT_CONTEXT_KEY == "spakky.auth.context"
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY == "spakky.auth.context_snapshot"
    assert AUTH_CONTEXT_SNAPSHOT_HEADER_KEY == "x-spakky-auth-context-snapshot"
    assert AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION == 1
    assert DEFAULT_AUTH_CLOCK_SKEW_SECONDS == 60
    assert AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY == (
        "auth.capability.validation.error"
    )


def test_auth_startup_contracts_are_exported_from_package_root() -> None:
    diagnostic = AuthStartupCapabilityDiagnostic(
        capability=AuthCapability.AUTHENTICATION,
        provider_count=0,
        provider_ids=(),
        required_by=("protected",),
    )
    error = AuthStartupCapabilityValidationError(diagnostics=(diagnostic,))

    assert AuthSnapshotPropagationConfig(enabled=True).enabled
    assert error.diagnostics == (diagnostic,)
    assert issubclass(AuthStartupContainerUnavailableError, AbstractSpakkyAuthError)
    assert error.startup_diagnostic_details[0].key == (
        AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY
    )


def test_credential_carrier_preserves_boundary_local_material() -> None:
    carrier = CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
        material="Bearer token",
        name="authorization",
        scheme="Bearer",
    )

    assert carrier.kind == CredentialCarrierKind.BEARER_TOKEN
    assert carrier.location == CredentialCarrierLocation.AUTHORIZATION_HEADER
    assert carrier.material == "Bearer token"
    assert carrier.name == "authorization"
    assert carrier.scheme == "Bearer"


def test_auth_context_round_trips_through_application_context_values() -> None:
    application_context = ApplicationContext()
    auth_context = AuthContext(
        subject=AuthSubject(id="user-1", display_name="User One"),
        issuer="issuer-1",
        tenant="tenant-1",
        roles=("role:admin",),
        scopes=("documents:read",),
        claims=(AuthClaim(name="email", value="user@example.com"),),
    )

    store_auth_context(application_context, auth_context)

    assert require_auth_context(application_context) == auth_context


def test_require_auth_context_rejects_missing_context_value() -> None:
    application_context = ApplicationContext()

    with pytest.raises(AuthContextNotFoundError):
        require_auth_context(application_context)


def test_require_auth_context_rejects_invalid_context_value() -> None:
    application_context = ApplicationContext()
    application_context.set_context_value(AUTH_CONTEXT_CONTEXT_KEY, "not auth context")

    with pytest.raises(InvalidAuthContextValueError):
        require_auth_context(application_context)


def test_authorization_decision_states_and_default_snapshot_mapping() -> None:
    assert {state.value for state in AuthorizationDecisionState} == {
        "ALLOW",
        "CHALLENGE",
        "DENY",
        "ERROR",
    }
    assert AuthorizationDecision.allow() == AuthorizationDecision(
        state=AuthorizationDecisionState.ALLOW,
        reason_code=AuthorizationReasonCode.AUTHORIZED,
    )
    assert AuthorizationDecision.challenge(
        AuthorizationReasonCode.MISSING_CREDENTIAL,
        "login required",
    ) == AuthorizationDecision(
        state=AuthorizationDecisionState.CHALLENGE,
        reason_code=AuthorizationReasonCode.MISSING_CREDENTIAL,
        reason="login required",
    )
    assert (
        AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE).state
        == AuthorizationDecisionState.DENY
    )
    assert (
        AuthorizationDecision.error(AuthorizationReasonCode.INTERNAL_ERROR).state
        == AuthorizationDecisionState.ERROR
    )
    assert MISSING_SNAPSHOT_DECISION.state == AuthorizationDecisionState.CHALLENGE
    assert INVALID_SNAPSHOT_DECISION.state == AuthorizationDecisionState.CHALLENGE
    assert EXPIRED_SNAPSHOT_DECISION.state == AuthorizationDecisionState.CHALLENGE
    assert (
        VERIFICATION_PROVIDER_UNAVAILABLE_DECISION.state
        == AuthorizationDecisionState.ERROR
    )


def test_auth_context_snapshot_produces_canonical_base64url_signed_envelope() -> None:
    snapshot = AuthContextSnapshot(
        subject=AuthSubject(id="user-1", display_name="User One"),
        issuer="issuer-1",
        issued_at=datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC),
        expires_at=datetime(2026, 5, 15, 1, 7, 3, tzinfo=UTC),
        tenant="tenant-1",
        roles=("role:admin",),
        scopes=("documents:read", "documents:write"),
        selected_claims=(
            AuthClaim(name="email", value="user@example.com"),
            AuthClaim(name="age", value=42),
        ),
        correlation_id="corr-1",
        delegation_chain=("service:a", "service:b"),
        signature=AuthContextSnapshotSignature(
            key_id="key-1",
            algorithm="ed25519",
            signature="signature-bytes",
        ),
    )

    payload = snapshot.canonical_payload()
    envelope = snapshot.canonical_json()
    encoded = snapshot.base64url_canonical_json()
    padding = "=" * (-len(encoded) % 4)
    decoded = urlsafe_b64decode(f"{encoded}{padding}").decode()

    assert payload["schema_version"] == AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION
    assert payload["selected_claims"] == {
        "age": 42,
        "email": "user@example.com",
    }
    assert payload["signature"] == {
        "algorithm": "ed25519",
        "key_id": "key-1",
        "signature": "signature-bytes",
    }
    assert envelope == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert decoded == envelope
    assert "=" not in encoded


def test_auth_error_hierarchy_is_framework_scoped() -> None:
    assert issubclass(AuthenticationError, AbstractSpakkyAuthError)
    assert issubclass(AuthorizationError, AbstractSpakkyAuthError)
    assert issubclass(ConflictingAuthMetadataError, AuthorizationError)
    assert issubclass(AuthRequirementDeniedError, AuthorizationError)
    assert issubclass(AuthRequirementProviderUnavailableError, AuthorizationError)
    assert issubclass(AuthContextSnapshotError, AbstractSpakkyAuthError)
    assert issubclass(
        AuthVerificationProviderUnavailableError,
        AuthContextSnapshotError,
    )


def test_public_auth_decorators_are_exported_from_package_root() -> None:
    @require_relation("owner", resource="document:1")
    @require_policy("document:1", "read")
    @require_permission("documents:read", resource="document:1")
    @require_role("role:admin")
    @require_scope("documents:read")
    @protected
    def protected_boundary() -> str:
        return "protected"

    @public_access
    def public_boundary() -> str:
        return "public"

    protected_metadata = get_effective_auth_metadata(protected_boundary)
    public_metadata = get_effective_auth_metadata(public_boundary)

    assert has_auth_boundary_metadata(protected_boundary)
    assert has_auth_boundary_metadata(public_boundary)
    assert protected_metadata.protected
    assert public_metadata.public_access
    assert PublicAccess.exists(public_boundary)
    assert all(
        isinstance(item, AuthRequirement) for item in protected_metadata.requirements
    )
    assert all(
        item.kind in AuthRequirementKind for item in protected_metadata.requirements
    )
    assert len(ProtectedRequirement.all(protected_boundary)) == 6
    assert AuthorizationAspect.__name__ == "AuthorizationAspect"
    assert AsyncAuthorizationAspect.__name__ == "AsyncAuthorizationAspect"
