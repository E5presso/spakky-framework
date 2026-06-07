# Spakky Auth

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 provider-neutral authentication and authorization core package입니다.

## 설치

```bash
pip install spakky-auth
```

## 현재 범위

`spakky-auth`는 인증/인가 마일스톤의 provider-neutral semantic model과 public provider contract를 소유합니다. Provider plugin과 boundary integration이 의존할 수 있는 `spakky.auth` import root, package metadata, workspace registration, documentation API path와 함께 다음 core 계약을 제공합니다.

- `AuthContext`, `AuthSubject`, `AuthClaim`: inbound adapter가 사용자 호출 전에 `ApplicationContext` context value에 seed하는 인증 상태
- `CredentialCarrier`: provider가 해석할 boundary-local credential 전달체
- `AuthorizationDecision`, `AuthorizationDecisionState`, `AuthorizationReasonCode`: `ALLOW`, `CHALLENGE`, `DENY`, `ERROR` 판정 모델
- `AuthContextSnapshot`: raw bearer token 대신 task/broker/saga 등으로 전파하는 signed snapshot envelope 계약
- `AuthCapability`: authentication, policy evaluation, permission/role/scope/relation check, snapshot sign/verify, password hash/verify capability 선언
- `IAuthenticationProvider`, `IAuthorizationPolicyEvaluator`, `IPermissionChecker`, `IRoleChecker`, `IScopeChecker`, `IRelationChecker`, `IAuthContextSnapshotSigner`, `IAuthContextSnapshotVerifier`, `IPasswordHasher`, `IPasswordVerifier`: ABC + `abstractmethod` 기반 public provider port
- `AuthInvocation`, `AuthDynamicRef`, `IAuthInvocationResolver`: resource/action/tenant dynamic ref를 invocation에서 resolve하기 위한 provider-neutral 계약
- `AuthProviderContribution`: `spakky.contributions.spakky.auth` feature-local contribution이 capability set을 선언하기 위한 metadata 계약
- `AuthSnapshotPropagationConfig`: signed `AuthContextSnapshot` 전파 사용 여부를 선언하는 feature-local config
- `public_access`, `protected`, `require_scope`, `require_role`, `require_permission`, `require_policy`, `require_relation`: class/function boundary에 public/protected auth metadata를 선언하는 Spakky-native decorator
- `get_effective_auth_metadata`: class-level과 method-level requirement를 AND semantics로 결합하고 exact duplicate canonical requirement를 idempotent하게 deduplicate하는 metadata aggregation API
- `AuthorizationAspect`, `AsyncAuthorizationAspect`: request-scope `AuthContext`를 읽어 protected metadata를 sync/async AOP로 enforcement하는 component
- `AuthCapabilityStartupValidationService`: plugin load/scan 이후 service start 이전에 protected metadata와 snapshot propagation config가 요구하는 `AuthCapability` 제공자 count를 검증하는 startup service
- `AbstractSpakkyAuthError` 기반 auth 오류 hierarchy

Provider implementation과 boundary integration은 후속 이슈에서 추가됩니다. Decorator가 없는 boundary는 allow all이며, protected/decorated boundary는 request-scope `AuthContext`와 provider-neutral checker port를 통해 fail closed로 처리됩니다.

## Decorator Metadata & AOP Enforcement

Public boundary는 `@public_access`로 명시하고, 인증만 필요한 boundary는 `@protected`로 표시합니다. 권한 requirement는 다음 decorator로 추가합니다.

```python
from spakky.auth import protected, require_role, require_scope


@require_role("role:admin")
class DocumentController:
    @require_scope("documents:read")
    @protected
    def read(self) -> str:
        return "ok"
```

Stacked requirement는 canonical `AuthRequirement` tuple로 aggregate되며, exact duplicate는 제거됩니다. Class-level requirement와 method-level requirement는 AND semantics로 결합됩니다. `public_access`와 protected requirement가 effective metadata에서 동시에 관찰되면 `ConflictingAuthMetadataError`가 발생합니다. OR/ANY semantics는 decorator 조합이 아니라 후속 `spakky-policy` named policy로 표현합니다.

`AuthorizationAspect`와 `AsyncAuthorizationAspect`는 메서드 인자로 `AuthContext`를 요구하지 않습니다. 각 inbound adapter가 `ApplicationContext` request/context scope에 seed한 `AuthContext`를 `require_auth_context()`로 읽고, provider-neutral checker port decision이 `ALLOW`가 아니면 `AuthRequirementDeniedError`로 실패합니다. 이 오류는 non-ALLOW `AuthorizationDecision`을 `decision` 속성에 보존하므로 inbound adapter는 원래 reason code를 CLI/HTTP/gRPC 등 transport별 응답으로 매핑할 수 있습니다.

## Provider Contribution Contract

Auth provider plugin은 base plugin entry point와 별도로 `spakky.contributions.spakky.auth` contribution entry point를 선언하고, 해당 contribution에서 `AuthProviderContribution` capability set과 필요한 port 구현 Pod을 등록합니다. Core `spakky-auth`는 provider plugin 이름이나 provider-specific 문자열로 분기하지 않습니다. Capability count 검증과 protected boundary enforcement는 feature-local startup validation 및 AOP로 연결됩니다.

## Startup Capability Validation

`initialize()`는 `AuthCapabilityStartupValidationService`를 등록합니다. 이 service는 `load_plugins()`와 `scan()`으로 등록된 Pod metadata 및 `AuthProviderContribution` contribution을 기준으로 service lifecycle start 전에 fail-fast validation을 수행합니다.

- protected metadata가 하나라도 있으면 `AUTHENTICATION` capability 제공자가 정확히 1개 필요합니다.
- `require_permission`, `require_role`, `require_scope`, `require_policy`, `require_relation` metadata는 각각 `PERMISSION_CHECK`, `ROLE_CHECK`, `SCOPE_CHECK`, `POLICY_EVALUATION`, `RELATION_CHECK` 제공자가 정확히 1개 필요합니다.
- enabled `AuthSnapshotPropagationConfig`가 있으면 `SNAPSHOT_SIGN`, `SNAPSHOT_VERIFY` 제공자가 각각 정확히 1개 필요합니다.
- protected usage와 enabled snapshot propagation config가 모두 없으면 provider가 없어도 startup fatal이 아닙니다.

count가 0 또는 2 이상이면 `AuthStartupCapabilityValidationError`가 발생하며, 각 mismatch는 `auth.capability.validation.error` startup diagnostic detail로 노출됩니다. 이 검증은 `spakky-auth` feature-local capability count 확인만 수행하며 generic contribution routing이나 provider priority/routing은 구현하지 않습니다.

## Context & Snapshot Keys

`AuthContext`는 `spakky.auth.context` key로 `ApplicationContext.set_context_value()`에 저장됩니다. 편의 함수 `store_auth_context()`와 `require_auth_context()`는 이 key를 사용합니다.

`AuthContextSnapshot` 전파 key는 다음과 같습니다.

| 용도 | Key |
|------|-----|
| metadata | `spakky.auth.context_snapshot` |
| header | `x-spakky-auth-context-snapshot` |

snapshot envelope는 schema version, subject, issuer, tenant, roles, scopes, selected claims, issued/expires timestamp, correlation id, delegation chain, signature material을 포함하는 canonical JSON을 unpadded base64url로 인코딩한 값입니다. 기본 clock skew는 60초입니다.

missing, invalid, expired snapshot은 기본적으로 `CHALLENGE` decision이며, verification provider unavailable은 `ERROR` decision입니다.

## Plugin Entry Point

패키지는 Spakky plugin discovery를 위해 다음 entry point를 등록합니다.

```toml
[project.entry-points."spakky.plugins"]
spakky-auth = "spakky.auth.main:initialize"
```

현재 `initialize()`는 `AuthCapabilityStartupValidationService`, `AuthorizationAspect`, `AsyncAuthorizationAspect`를 등록합니다. 후속 이슈에서 boundary integration이 추가되면 같은 entry point를 통해 feature-local component를 등록합니다.

## 개발 검증

패키지 단위 검증은 패키지 디렉토리에서 실행합니다.

```bash
cd core/spakky-auth
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 `pyproject.toml`의 coverage 설정을 사용하며 `src/spakky/auth/**/*.py`에 대해 100% coverage를 요구합니다.

## 라이선스

MIT License
