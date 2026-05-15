"""ABC ports for provider-neutral auth providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from spakky.auth.context import AuthContext
from spakky.auth.credential import CredentialCarrier
from spakky.auth.decision import AuthorizationDecision
from spakky.auth.invocation import (
    AuthActionRef,
    AuthDynamicRef,
    AuthInvocation,
    AuthPermissionRef,
    AuthRelationRef,
    AuthResourceRef,
    AuthRoleRef,
    AuthScopeRef,
    AuthTenantRef,
    ResolvedAuthReference,
)
from spakky.auth.snapshot import AuthContextSnapshot

type AuthPasswordPlaintext = str
type AuthPasswordHash = str


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationRequest:
    """Provider-neutral policy evaluation request."""

    auth_context: AuthContext
    """Authenticated subject context."""

    resource: AuthResourceRef
    """Canonical resource reference being accessed."""

    action: AuthActionRef
    """Canonical action reference being attempted."""

    tenant: AuthTenantRef | None = None
    """Optional tenant reference; None means tenant is not applicable."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionCheckRequest:
    """Permission check request scoped to an authenticated subject."""

    auth_context: AuthContext
    """Authenticated subject context."""

    permission: AuthPermissionRef
    """Canonical permission reference."""

    resource: AuthResourceRef | None = None
    """Optional resource reference; None means resource-independent."""

    tenant: AuthTenantRef | None = None
    """Optional tenant reference; None means tenant is not applicable."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleCheckRequest:
    """Role check request scoped to an authenticated subject."""

    auth_context: AuthContext
    """Authenticated subject context."""

    role: AuthRoleRef
    """Canonical role reference."""

    tenant: AuthTenantRef | None = None
    """Optional tenant reference; None means tenant is not applicable."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeCheckRequest:
    """Scope check request scoped to an authenticated subject."""

    auth_context: AuthContext
    """Authenticated subject context."""

    scope: AuthScopeRef
    """Canonical scope reference."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RelationCheckRequest:
    """Relationship authorization request scoped to a resource."""

    auth_context: AuthContext
    """Authenticated subject context."""

    relation: AuthRelationRef
    """Canonical relationship reference."""

    resource: AuthResourceRef
    """Canonical resource reference for the relationship check."""

    tenant: AuthTenantRef | None = None
    """Optional tenant reference; None means tenant is not applicable."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotSignRequest:
    """Request for signing an AuthContext snapshot for propagation."""

    auth_context: AuthContext
    """Auth context to serialize and sign."""

    tenant: AuthTenantRef | None = None
    """Optional tenant override; None means use the context tenant."""


class IAuthenticationProvider(ABC):
    """Provider-neutral authentication port."""

    @abstractmethod
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        """Authenticate a credential observed at an invocation boundary."""
        ...


class IAuthorizationPolicyEvaluator(ABC):
    """Provider-neutral policy evaluation port."""

    @abstractmethod
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        """Evaluate a resource/action authorization request."""
        ...


class IPermissionChecker(ABC):
    """Provider-neutral permission check port."""

    @abstractmethod
    def check_permission(
        self, request: PermissionCheckRequest
    ) -> AuthorizationDecision:
        """Check whether a subject has a permission."""
        ...


class IRoleChecker(ABC):
    """Provider-neutral role check port."""

    @abstractmethod
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        """Check whether a subject has a role."""
        ...


class IScopeChecker(ABC):
    """Provider-neutral scope check port."""

    @abstractmethod
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        """Check whether a subject has a scope."""
        ...


class IRelationChecker(ABC):
    """Provider-neutral relation check port."""

    @abstractmethod
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        """Check whether a subject has a relation to a resource."""
        ...


class IAuthContextSnapshotSigner(ABC):
    """Provider-neutral AuthContextSnapshot signing port."""

    @abstractmethod
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        """Create a signed AuthContextSnapshot for propagation."""
        ...


class IAuthContextSnapshotVerifier(ABC):
    """Provider-neutral AuthContextSnapshot verification port."""

    @abstractmethod
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        """Verify a signed snapshot envelope and return its auth context."""
        ...


class IPasswordHasher(ABC):
    """Provider-neutral password hashing port."""

    @abstractmethod
    def hash_password(self, password: AuthPasswordPlaintext) -> AuthPasswordHash:
        """Hash plaintext password material for storage."""
        ...


class IPasswordVerifier(ABC):
    """Provider-neutral password verification port."""

    @abstractmethod
    def verify_password(
        self,
        password: AuthPasswordPlaintext,
        password_hash: AuthPasswordHash,
    ) -> AuthorizationDecision:
        """Verify plaintext password material against a stored hash."""
        ...


class IAuthInvocationResolver(ABC):
    """Resolver for invocation-scoped resource, action, and tenant refs."""

    @abstractmethod
    def resolve_ref(
        self,
        invocation: AuthInvocation,
        dynamic_ref: AuthDynamicRef,
    ) -> ResolvedAuthReference:
        """Resolve a late-bound auth reference from invocation attributes."""
        ...
