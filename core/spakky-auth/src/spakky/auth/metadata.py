"""Decorator metadata contracts for protected auth boundaries."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from inspect import getmembers_static

from spakky.auth.error import ConflictingAuthMetadataError
from spakky.auth.invocation import (
    AuthActionRef,
    AuthPermissionRef,
    AuthRelationRef,
    AuthResourceRef,
    AuthRoleRef,
    AuthScopeRef,
    AuthTenantRef,
)
from spakky.core.common.annotation import Annotation

AUTHENTICATED_REQUIREMENT_REF = "authenticated"


class AuthRequirementKind(StrEnum):
    """Canonical auth requirement categories supported by decorators."""

    AUTHENTICATED = "AUTHENTICATED"
    PERMISSION = "PERMISSION"
    POLICY = "POLICY"
    RELATION = "RELATION"
    ROLE = "ROLE"
    SCOPE = "SCOPE"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthRequirement:
    """Canonical protected-boundary auth requirement."""

    kind: AuthRequirementKind
    """Requirement category used by enforcement to select the provider port."""

    ref: str
    """Canonical permission, role, scope, relation, or marker reference."""

    resource: AuthResourceRef | None = None
    """Optional resource reference for permission, policy, or relation checks."""

    action: AuthActionRef | None = None
    """Optional action reference for policy checks."""

    tenant: AuthTenantRef | None = None
    """Optional tenant reference for tenant-scoped checks."""


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectiveAuthMetadata:
    """Effective auth metadata after class/method aggregation."""

    public_access: bool
    """Whether a public access marker is effective."""

    requirements: tuple[AuthRequirement, ...]
    """Ordered, duplicate-free protected requirements with AND semantics."""

    @property
    def protected(self) -> bool:
        """Return whether this boundary has protected requirements."""
        return len(self.requirements) > 0


@dataclass
class PublicAccess(Annotation):
    """Marker annotation for explicitly public boundaries."""

    ...


@dataclass
class ProtectedRequirement(Annotation):
    """Annotation carrying one protected auth requirement."""

    requirement: AuthRequirement


def public_access[T: object](obj: T) -> T:
    """Mark a class or method as explicitly public."""
    return PublicAccess()(obj)


def protected[T: object](obj: T) -> T:
    """Require an authenticated request-scope AuthContext."""
    return _requirement_decorator(
        AuthRequirement(
            kind=AuthRequirementKind.AUTHENTICATED,
            ref=AUTHENTICATED_REQUIREMENT_REF,
        )
    )(obj)


def require_permission[T: object](
    permission: AuthPermissionRef,
    *,
    resource: AuthResourceRef | None = None,
    tenant: AuthTenantRef | None = None,
) -> Callable[[T], T]:
    """Require a permission decision for a class or method boundary."""
    return _requirement_decorator(
        AuthRequirement(
            kind=AuthRequirementKind.PERMISSION,
            ref=permission,
            resource=resource,
            tenant=tenant,
        )
    )


def require_policy[T: object](
    resource: AuthResourceRef,
    action: AuthActionRef,
    *,
    tenant: AuthTenantRef | None = None,
) -> Callable[[T], T]:
    """Require a resource/action policy decision for a boundary."""
    return _requirement_decorator(
        AuthRequirement(
            kind=AuthRequirementKind.POLICY,
            ref=resource,
            resource=resource,
            action=action,
            tenant=tenant,
        )
    )


def require_relation[T: object](
    relation: AuthRelationRef,
    *,
    resource: AuthResourceRef,
    tenant: AuthTenantRef | None = None,
) -> Callable[[T], T]:
    """Require a relationship decision for a resource boundary."""
    return _requirement_decorator(
        AuthRequirement(
            kind=AuthRequirementKind.RELATION,
            ref=relation,
            resource=resource,
            tenant=tenant,
        )
    )


def require_role[T: object](
    role: AuthRoleRef,
    *,
    tenant: AuthTenantRef | None = None,
) -> Callable[[T], T]:
    """Require a role decision for a class or method boundary."""
    return _requirement_decorator(
        AuthRequirement(
            kind=AuthRequirementKind.ROLE,
            ref=role,
            tenant=tenant,
        )
    )


def require_scope[T: object](scope: AuthScopeRef) -> Callable[[T], T]:
    """Require a scope decision for a class or method boundary."""
    return _requirement_decorator(
        AuthRequirement(kind=AuthRequirementKind.SCOPE, ref=scope)
    )


def get_effective_auth_metadata(
    obj: object,
    *,
    owner_type: type[object] | None = None,
) -> EffectiveAuthMetadata:
    """Aggregate class and method auth metadata using AND semantics."""
    sources = _metadata_sources(obj, owner_type=owner_type)
    public = any(PublicAccess.exists(source) for source in sources)
    requirements = _dedupe_requirements(
        requirement.requirement
        for source in sources
        for requirement in ProtectedRequirement.all(source)
    )
    if public and requirements:
        raise ConflictingAuthMetadataError()
    return EffectiveAuthMetadata(public_access=public, requirements=requirements)


def has_auth_boundary_metadata(obj: object) -> bool:
    """Return whether an object or any method declares auth metadata."""
    if _source_has_auth_metadata(obj):
        return True
    if isinstance(obj, type):
        return _type_has_method_auth_metadata(obj)
    if callable(obj):
        owner_type = _owner_type(obj)
        if owner_type is None:
            return _source_has_auth_metadata(obj)
        return _source_has_auth_metadata(owner_type) or _source_has_auth_metadata(obj)
    return _source_has_auth_metadata(type(obj)) or _type_has_method_auth_metadata(
        type(obj)
    )


def _requirement_decorator[T: object](
    requirement: AuthRequirement,
) -> Callable[[T], T]:
    def decorator(obj: T) -> T:
        return ProtectedRequirement(requirement=requirement)(obj)

    return decorator


def _metadata_sources(
    obj: object,
    *,
    owner_type: type[object] | None,
) -> tuple[object, ...]:
    if isinstance(obj, type):
        return (obj,)
    resolved_owner = owner_type if owner_type is not None else _owner_type(obj)
    if resolved_owner is None:
        return (obj,)
    return (resolved_owner, obj)


def _owner_type(obj: object) -> type[object] | None:
    owner = getattr(  # framework decorator metadata must support bound methods
        obj, "__self__", None
    )
    if isinstance(owner, type):
        return owner
    if owner is None:
        return None
    return type(owner)


def _source_has_auth_metadata(source: object) -> bool:
    return PublicAccess.exists(source) or len(ProtectedRequirement.all(source)) > 0


def _type_has_method_auth_metadata(owner_type: type[object]) -> bool:
    for _, member in getmembers_static(owner_type):
        if callable(member) and _source_has_auth_metadata(member):
            return True
    return False


def _dedupe_requirements(
    requirements: Iterable[AuthRequirement],
) -> tuple[AuthRequirement, ...]:
    ordered: list[AuthRequirement] = []
    seen: set[AuthRequirement] = set()
    for requirement in requirements:
        if requirement not in seen:
            ordered.append(requirement)
            seen.add(requirement)
    return tuple(ordered)
