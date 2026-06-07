"""RBAC, PBAC, and ABAC-style policy document evaluator."""

from dataclasses import dataclass

from spakky.auth import (
    AuthClaim,
    AuthContext,
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthorizationRequest,
    PermissionCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.plugins.policy.model import (
    ClaimValue,
    ConditionComposition,
    ConditionOperator,
    NamedPolicy,
    PolicyCondition,
    PolicyDocument,
    PolicyEffect,
    PolicyEvaluationEvidence,
    PolicyEvaluationResult,
    PolicyEvidenceKind,
    PolicyRef,
    PolicyStatement,
    PolicySubject,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyEvaluationInput:
    """Provider-native policy evaluation input."""

    auth_context: AuthContext
    resource: PolicyRef | None = None
    action: PolicyRef | None = None
    tenant: PolicyRef | None = None
    permission: PolicyRef | None = None
    role: PolicyRef | None = None
    scope: PolicyRef | None = None
    policy: PolicyRef | None = None


class PolicyDocumentEvaluator:
    """Evaluate canonical Spakky policy documents."""

    _document: PolicyDocument
    _subjects: dict[PolicyRef, PolicySubject]
    _roles: dict[PolicyRef, tuple[PolicyRef, ...]]
    _scopes: dict[PolicyRef, tuple[PolicyRef, ...]]
    _policies: dict[PolicyRef, NamedPolicy]
    _conditions: dict[PolicyRef, PolicyCondition]

    def __init__(self, document: PolicyDocument) -> None:
        self._document = document
        self._subjects = {subject.ref: subject for subject in document.subjects}
        self._roles = {role.ref: role.permissions for role in document.roles}
        self._scopes = {scope.ref: scope.permissions for scope in document.scopes}
        self._policies = {policy.ref: policy for policy in document.policies}
        self._conditions = {
            condition.ref: condition
            for condition in document.conditions
            if condition.ref is not None
        }

    def evaluate(self, request: PolicyEvaluationInput) -> PolicyEvaluationResult:
        """Evaluate a request with deny precedence and default deny."""
        evidence: list[PolicyEvaluationEvidence] = []
        allow_seen = False
        for policy in self._selected_policies(request.policy):
            for statement in policy.statements:
                if self._statement_matches(statement, request, evidence, policy.ref):
                    evidence.append(
                        PolicyEvaluationEvidence(
                            kind=PolicyEvidenceKind.STATEMENT_MATCHED,
                            policy=policy.ref,
                            statement=statement.ref,
                            reason=f"{statement.effect.value} statement matched",
                        )
                    )
                    if statement.effect is PolicyEffect.DENY:
                        return PolicyEvaluationResult(
                            allowed=False,
                            effect=PolicyEffect.DENY,
                            evidence=tuple(evidence),
                        )
                    allow_seen = True
                else:
                    evidence.append(
                        PolicyEvaluationEvidence(
                            kind=PolicyEvidenceKind.STATEMENT_SKIPPED,
                            policy=policy.ref,
                            statement=statement.ref,
                            reason="statement did not match request",
                        )
                    )
        if allow_seen:
            return PolicyEvaluationResult(
                allowed=True,
                effect=PolicyEffect.ALLOW,
                evidence=tuple(evidence),
            )
        evidence.append(
            PolicyEvaluationEvidence(
                kind=PolicyEvidenceKind.DEFAULT_DENY,
                reason="no allow statement matched",
            )
        )
        return PolicyEvaluationResult(
            allowed=False,
            effect=None,
            evidence=tuple(evidence),
        )

    def evaluate_authorization(
        self,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        """Map resource/action policy evaluation to AuthorizationDecision."""
        result = self.evaluate(
            PolicyEvaluationInput(
                auth_context=request.auth_context,
                resource=request.resource,
                action=request.action,
                tenant=request.tenant,
            )
        )
        return self._decision(result)

    def check_permission(
        self, request: PermissionCheckRequest
    ) -> AuthorizationDecision:
        """Check a canonical permission reference."""
        result = self.evaluate(
            PolicyEvaluationInput(
                auth_context=request.auth_context,
                resource=request.resource,
                tenant=request.tenant,
                permission=request.permission,
            )
        )
        return self._decision(result)

    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        """Check a canonical role reference."""
        result = self.evaluate(
            PolicyEvaluationInput(
                auth_context=request.auth_context,
                tenant=request.tenant,
                role=request.role,
            )
        )
        return self._decision(result)

    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        """Check a canonical scope reference."""
        result = self.evaluate(
            PolicyEvaluationInput(
                auth_context=request.auth_context,
                scope=request.scope,
            )
        )
        return self._decision(result)

    def _selected_policies(
        self, policy_ref: PolicyRef | None
    ) -> tuple[NamedPolicy, ...]:
        if policy_ref is None:
            return self._document.policies
        policy = self._policies.get(policy_ref)
        if policy is None:
            return ()
        return (policy,)

    def _statement_matches(
        self,
        statement: PolicyStatement,
        request: PolicyEvaluationInput,
        evidence: list[PolicyEvaluationEvidence],
        policy_ref: PolicyRef,
    ) -> bool:
        return (
            self._matches_subject(statement, request.auth_context)
            and self._matches_roles(statement, request.auth_context)
            and self._matches_scopes(statement, request.auth_context)
            and self._matches_permissions(statement, request)
            and self._matches_requested_permission(statement, request)
            and self._matches_resources(statement, request.resource)
            and self._matches_actions(statement, request.action)
            and self._matches_tenants(statement, request)
            and self._matches_requested_role(statement, request.role)
            and self._matches_requested_scope(statement, request.scope)
            and self._matches_condition(statement, request, evidence, policy_ref)
        )

    def _matches_subject(
        self,
        statement: PolicyStatement,
        auth_context: AuthContext,
    ) -> bool:
        if not statement.subjects:
            return True
        return auth_context.subject.id in statement.subjects

    def _matches_roles(
        self,
        statement: PolicyStatement,
        auth_context: AuthContext,
    ) -> bool:
        if not statement.roles:
            return True
        return self._intersects(statement.roles, self._subject_roles(auth_context))

    def _matches_scopes(
        self,
        statement: PolicyStatement,
        auth_context: AuthContext,
    ) -> bool:
        if not statement.scopes:
            return True
        return self._intersects(statement.scopes, self._subject_scopes(auth_context))

    def _matches_permissions(
        self,
        statement: PolicyStatement,
        request: PolicyEvaluationInput,
    ) -> bool:
        if not statement.permissions:
            return True
        subject_permissions = self._subject_permissions(request.auth_context)
        return self._intersects(statement.permissions, subject_permissions)

    def _matches_requested_permission(
        self,
        statement: PolicyStatement,
        request: PolicyEvaluationInput,
    ) -> bool:
        if request.permission is None:
            return True
        if statement.permissions and request.permission not in statement.permissions:
            return False
        return request.permission in self._subject_permissions(request.auth_context)

    def _matches_resources(
        self,
        statement: PolicyStatement,
        resource: PolicyRef | None,
    ) -> bool:
        if not statement.resources:
            return True
        if resource is None:
            return False
        return resource in statement.resources

    def _matches_actions(
        self,
        statement: PolicyStatement,
        action: PolicyRef | None,
    ) -> bool:
        if not statement.actions:
            return True
        if action is None:
            return False
        return action in statement.actions

    def _matches_tenants(
        self,
        statement: PolicyStatement,
        request: PolicyEvaluationInput,
    ) -> bool:
        if not statement.tenants:
            return True
        tenant = (
            request.tenant
            if request.tenant is not None
            else request.auth_context.tenant
        )
        if tenant is None:
            return False
        return tenant in statement.tenants

    def _matches_requested_role(
        self,
        statement: PolicyStatement,
        role: PolicyRef | None,
    ) -> bool:
        return role is None or not statement.roles or role in statement.roles

    def _matches_requested_scope(
        self,
        statement: PolicyStatement,
        scope: PolicyRef | None,
    ) -> bool:
        return scope is None or not statement.scopes or scope in statement.scopes

    def _matches_condition(
        self,
        statement: PolicyStatement,
        request: PolicyEvaluationInput,
        evidence: list[PolicyEvaluationEvidence],
        policy_ref: PolicyRef,
    ) -> bool:
        if statement.condition is None:
            return True
        matched = self._condition_matches(statement.condition, request.auth_context)
        evidence.append(
            PolicyEvaluationEvidence(
                kind=(
                    PolicyEvidenceKind.CONDITION_MATCHED
                    if matched
                    else PolicyEvidenceKind.CONDITION_FAILED
                ),
                policy=policy_ref,
                statement=statement.ref,
                reason="statement condition matched"
                if matched
                else "statement condition failed",
            )
        )
        return matched

    def _condition_matches(
        self,
        condition: PolicyCondition,
        auth_context: AuthContext,
    ) -> bool:
        resolved = self._resolve_condition(condition)
        if resolved.composition is ConditionComposition.ALL:
            return all(
                self._condition_matches(child, auth_context)
                for child in resolved.children
            )
        if resolved.composition is ConditionComposition.ANY:
            return any(
                self._condition_matches(child, auth_context)
                for child in resolved.children
            )
        if resolved.composition is ConditionComposition.NOT:
            child = resolved.children[0]
            return not self._condition_matches(child, auth_context)
        return self._operator_matches(
            resolved.operator,
            self._claim_value(auth_context.claims, resolved.key),
            resolved.value,
        )

    def _resolve_condition(self, condition: PolicyCondition) -> PolicyCondition:
        if (
            condition.operator is None
            and condition.composition is None
            and condition.ref is not None
        ):
            named = self._conditions.get(condition.ref)
            if named is not None:
                return named
        return condition

    def _operator_matches(
        self,
        operator: ConditionOperator | None,
        actual: ClaimValue,
        expected: ClaimValue | tuple[ClaimValue, ...],
    ) -> bool:
        if operator is ConditionOperator.EXISTS:
            return actual is not None
        if operator is ConditionOperator.EQUALS:
            return actual == expected
        if operator is ConditionOperator.NOT_EQUALS:
            return actual != expected
        if operator is ConditionOperator.IN:
            if isinstance(expected, tuple):
                return actual in expected
            return actual == expected
        if operator is ConditionOperator.CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            return False
        return False

    def _claim_value(
        self,
        claims: tuple[AuthClaim, ...],
        key: str | None,
    ) -> ClaimValue:
        if key is None:
            return None
        for claim in claims:
            if claim.name == key:
                return claim.value
        return None

    def _subject_roles(self, auth_context: AuthContext) -> tuple[PolicyRef, ...]:
        subject = self._subjects.get(auth_context.subject.id)
        if subject is None:
            return auth_context.roles
        return (*auth_context.roles, *subject.roles)

    def _subject_scopes(self, auth_context: AuthContext) -> tuple[PolicyRef, ...]:
        subject = self._subjects.get(auth_context.subject.id)
        if subject is None:
            return auth_context.scopes
        return (*auth_context.scopes, *subject.scopes)

    def _subject_permissions(self, auth_context: AuthContext) -> tuple[PolicyRef, ...]:
        permissions: list[PolicyRef] = []
        subject = self._subjects.get(auth_context.subject.id)
        if subject is not None:
            permissions.extend(subject.permissions)
            for role_ref in subject.roles:
                permissions.extend(self._role_permissions(role_ref))
            for scope_ref in subject.scopes:
                permissions.extend(self._scope_permissions(scope_ref))
        for role_ref in auth_context.roles:
            permissions.extend(self._role_permissions(role_ref))
        for scope_ref in auth_context.scopes:
            permissions.extend(self._scope_permissions(scope_ref))
        return tuple(dict.fromkeys(permissions))

    def _role_permissions(self, role_ref: PolicyRef) -> tuple[PolicyRef, ...]:
        return self._roles.get(role_ref, ())

    def _scope_permissions(self, scope_ref: PolicyRef) -> tuple[PolicyRef, ...]:
        return self._scopes.get(scope_ref, ())

    def _intersects(
        self,
        expected: tuple[PolicyRef, ...],
        actual: tuple[PolicyRef, ...],
    ) -> bool:
        actual_set = set(actual)
        return any(item in actual_set for item in expected)

    def _decision(self, result: PolicyEvaluationResult) -> AuthorizationDecision:
        if result.allowed:
            return AuthorizationDecision.allow()
        return AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)
