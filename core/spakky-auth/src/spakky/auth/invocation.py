"""Provider-neutral invocation and dynamic auth reference contracts."""

from dataclasses import dataclass
from enum import StrEnum

from spakky.auth.context import AuthSubject

type AuthActionRef = str
type AuthBoundaryRef = str
type AuthInvocationAttributeName = str
type AuthInvocationOperationRef = str
type AuthPermissionRef = str
type AuthRelationRef = str
type AuthResourceRef = str
type AuthRoleRef = str
type AuthScopeRef = str
type AuthTenantRef = str
type AuthDynamicRefExpression = str
type AuthInvocationAttributeValue = str | int | float | bool | None
type AuthResolvedRef = AuthResourceRef | AuthActionRef | AuthTenantRef


class AuthDynamicRefKind(StrEnum):
    """Dynamic auth reference target kinds resolved from an invocation."""

    RESOURCE = "RESOURCE"
    ACTION = "ACTION"
    TENANT = "TENANT"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthInvocationAttribute:
    """Typed scalar attribute made available to auth reference resolvers."""

    name: AuthInvocationAttributeName
    """Provider-neutral attribute name."""

    value: AuthInvocationAttributeValue
    """JSON-scalar invocation attribute value."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthInvocation:
    """Provider-neutral description of the boundary call being authorized."""

    boundary: AuthBoundaryRef
    """Boundary category such as HTTP, gRPC, CLI, task, event, or saga."""

    operation: AuthInvocationOperationRef
    """Canonical operation or handler reference at the boundary."""

    subject: AuthSubject | None = None
    """Optional pre-authenticated subject when a boundary already has one."""

    attributes: tuple[AuthInvocationAttribute, ...] = ()
    """Scalar invocation attributes available to dynamic ref resolvers."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthDynamicRef:
    """Late-bound resource, action, or tenant reference expression."""

    kind: AuthDynamicRefKind
    """Reference kind expected from the resolver output."""

    expression: AuthDynamicRefExpression
    """Provider-neutral expression name understood by the resolver."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedAuthReference:
    """Resolved auth reference value returned by invocation resolvers."""

    kind: AuthDynamicRefKind
    """Resolved reference kind."""

    value: AuthResolvedRef
    """Canonical resource, action, or tenant reference."""
