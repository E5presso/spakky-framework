# 인증/인가

Spakky의 인증/인가는 `spakky-auth`가 공통 의미 모델을 소유하고, provider 플러그인이 실제 인증·인가 결정을 제공하며, 각 adapter가 실행 경계에서 `AuthContext`를 seed하거나 signed `AuthContextSnapshot`을 전파하는 구조입니다.

핵심 규칙은 단순합니다.

- decorator가 없는 boundary는 allow all입니다.
- `@protected`, `@require_scope`, `@require_role`, `@require_permission`, `@require_policy`, `@require_relation`이 붙은 boundary는 fail closed입니다.
- raw bearer token은 HTTP, WebSocket, gRPC, CLI 같은 inbound boundary에서만 credential로 읽습니다.
- task, broker, event, saga 전파에는 raw bearer token 대신 signed `AuthContextSnapshot`을 사용합니다.

---

## 패키지 구성

필요한 기능에 맞춰 core와 provider plugin을 함께 설치합니다.

```bash
pip install spakky-auth spakky-oidc spakky-policy spakky-openfga spakky-cryptography
```

애플리케이션은 auth core plugin과 실제 provider plugin을 함께 로드합니다. Provider contribution은 `spakky.contributions.spakky.auth` entry point로 capability를 선언하고, `spakky-auth` startup validation은 보호된 boundary와 snapshot propagation이 요구하는 capability가 정확히 1개인지 검사합니다.

```python
import spakky.auth
import spakky.plugins.cryptography
import spakky.plugins.oidc
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.oidc.PLUGIN_NAME,
            Plugin(name="spakky-policy"),
            spakky.plugins.cryptography.PLUGIN_NAME,
        }
    )
    .scan(apps)
    .start()
)
```

`spakky-openfga`는 relation check 또는 OpenFGA-backed policy evaluation이 필요할 때 추가합니다. `spakky-cryptography`는 signed snapshot 전파와 password hash/verify capability를 제공합니다.

---

## Decorator

Decorator는 class 또는 method boundary에 provider-neutral metadata를 붙입니다. 메서드는 `AuthContext`를 인자로 받을 필요가 없습니다. Adapter가 사용자 코드 호출 전에 `ApplicationContext` request/context scope에 context를 저장하고, `AuthorizationAspect` 또는 adapter wrapper가 metadata를 평가합니다.

```python
from spakky.auth import protected, require_role, require_scope
from spakky.plugins.fastapi.routes import get
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


@ApiController("/documents")
@require_role("role:editor")
class DocumentController:
    @get("/{document_id}")
    @require_scope("documents:read")
    @protected
    def read(self, document_id: str) -> dict[str, str]:
        return {"id": document_id}
```

Class-level requirement와 method-level requirement는 AND semantics로 결합됩니다. 같은 canonical requirement는 중복 제거됩니다. `@public_access`와 protected requirement가 같은 effective metadata에 함께 있으면 `ConflictingAuthMetadataError`로 시작 또는 호출이 실패합니다.

| Decorator | Provider capability |
| --- | --- |
| `@protected` | `AUTHENTICATION` |
| `@require_scope("documents:read")` | `SCOPE_CHECK` |
| `@require_role("role:admin")` | `ROLE_CHECK` |
| `@require_permission("documents:read", resource="document:1")` | `PERMISSION_CHECK` |
| `@require_policy("document:1", "read")` | `POLICY_EVALUATION` |
| `@require_relation("owner", resource="document:1")` | `RELATION_CHECK` |

OR/ANY 의미는 decorator 조합이 아니라 `spakky-policy`의 named policy로 표현합니다.

---

## Provider

### OIDC

`spakky-oidc`는 bearer JWT를 검증하고 `AuthContext`로 매핑하는 authentication provider입니다. 범위는 inbound bearer token 인증입니다. Browser login, callback, session, refresh, logout route는 제공하지 않습니다.

```python
from spakky.auth import (
    AuthInvocation,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
)
from spakky.plugins.oidc import OidcAuthenticationProvider, OidcProviderConfig

provider = OidcAuthenticationProvider(
    config=OidcProviderConfig(
        issuer="https://issuer.example.test",
        audience="api://spakky",
        client_id="spakky-client",
        roles_claim="roles",
        scopes_claim="scope",
        tenant_claim="tenant",
    )
)

auth_context = provider.authenticate(
    CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
        material="eyJ...",
        name="Authorization",
        scheme="Bearer",
    ),
    AuthInvocation(boundary="HTTP", operation="GET /documents"),
)
```

OIDC provider는 discovery document와 JWKS를 읽고, `kid` key selection, RS256 signature, issuer, audience, `azp`, `exp`, `nbf`, `iat`, clock skew를 검증합니다. `sub`, display name, tenant, roles, scopes, selected safe claims만 `AuthContext`에 남기며 raw bearer token은 claims, metadata, credential carrier에 보존하지 않습니다.

Failure mapping은 다음과 같습니다.

| Failure | Decision |
| --- | --- |
| missing bearer credential | `CHALLENGE / MISSING_CREDENTIAL` |
| malformed credential or invalid token | `CHALLENGE / INVALID_CREDENTIAL` |
| JWKS key selection failure | `CHALLENGE / INVALID_CREDENTIAL` |
| discovery/provider unavailable | `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` |

### Policy

`spakky-policy`는 YAML, TOML, JSON policy document를 typed model로 로드하고 RBAC, PBAC, ABAC-style rule을 평가합니다. Policy UI, generic policy API, MCP/tool authorization, authorized data filtering은 범위 밖입니다.

```python
from spakky.auth import AuthContext, AuthSubject
from spakky.plugins.policy import PolicyDocumentEvaluator, PolicyEvaluationInput
from spakky.plugins.policy.loader import policy_document_from_mapping

document = policy_document_from_mapping(
    {
        "version": "2026-06",
        "metadata": {"name": "document-policy"},
        "roles": [
            {"ref": "role:editor", "permissions": ["permission:documents-read"]}
        ],
        "policies": [
            {
                "ref": "policy:documents-read",
                "statements": [
                    {
                        "ref": "allow-editor-read",
                        "effect": "allow",
                        "roles": ["role:editor"],
                        "permissions": ["permission:documents-read"],
                        "resources": ["document:1"],
                        "actions": ["read"],
                    }
                ],
            }
        ],
    }
)

result = PolicyDocumentEvaluator(document).evaluate(
    PolicyEvaluationInput(
        auth_context=AuthContext(
            subject=AuthSubject(id="user:alice"),
            issuer="issuer:test",
            roles=("role:editor",),
        ),
        resource="document:1",
        action="read",
        policy="policy:documents-read",
    )
)
assert result.allowed
```

Explicit deny가 matching allow보다 우선합니다. Matching allow가 없으면 default deny evidence를 반환합니다. Conditions는 `all`, `any`, `not` composition과 `equals`, `not_equals`, `in`, `contains`, `exists` operator를 지원합니다.

### OpenFGA

`spakky-openfga`는 check-only OpenFGA provider입니다. Tuple write, authorization model migration, admin CLI/API, list resources, tuple/model management, data/query filtering은 제공하지 않습니다.

```bash
export SPAKKY_OPENFGA_API_URL=http://localhost:8080
export SPAKKY_OPENFGA_STORE_ID=store-id
export SPAKKY_OPENFGA_AUTHORIZATION_MODEL_ID=model-id
export SPAKKY_OPENFGA_PRINCIPAL_TYPE=user
export SPAKKY_OPENFGA_INCLUDE_TENANT_IN_OBJECT=true
```

`RelationCheckRequest.relation`과 `AuthorizationRequest.action`은 OpenFGA relation으로 매핑됩니다. `AuthContext.subject.id`는 OpenFGA user로 매핑되며 type prefix가 없으면 `principal_type`이 붙습니다. Tenant가 있으면 기본적으로 `<tenant>/<resource>` 형태로 object ref에 포함됩니다.

Provider unavailable은 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` decision입니다. 빈 canonical reference처럼 OpenFGA user/object/relation으로 매핑할 수 없는 값은 `ERROR / INTERNAL_ERROR` decision으로 반환됩니다.

### Cryptography

`spakky-cryptography`는 retained crypto utility와 auth provider capability를 함께 제공합니다.

- `SNAPSHOT_SIGN`, `SNAPSHOT_VERIFY`: `AuthContextSnapshot` HMAC envelope sign/verify
- `PASSWORD_HASH`, `PASSWORD_VERIFY`: password hash/verify port
- `Key`, `Base64Encoder`, `Hash`, `HMAC`, `Aes`, `Gcm`, `Rsa`, retained password encoders

```python
from datetime import timedelta

from spakky.auth import AuthContext, AuthInvocation, AuthSubject, SnapshotSignRequest
from spakky.plugins.cryptography import (
    CryptographyAuthProvider,
    CryptographyAuthProviderConfig,
)

provider = CryptographyAuthProvider(
    config=CryptographyAuthProviderConfig(snapshot_ttl=timedelta(minutes=5))
)
snapshot = provider.sign_snapshot(
    SnapshotSignRequest(
        auth_context=AuthContext(
            subject=AuthSubject(id="user:alice"),
            issuer="issuer:test",
            scopes=("documents:read",),
        )
    )
)
auth_context = provider.verify_snapshot(
    snapshot.base64url_canonical_json(),
    AuthInvocation(boundary="task", operation="documents.reindex"),
)
```

Missing, invalid, and expired snapshot envelopes map to `CHALLENGE`. Verification provider unavailable maps to `ERROR`. Password verification failure maps to `CHALLENGE / INVALID_CREDENTIAL`; password provider unavailable maps to `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE`.

---

## Boundary

### FastAPI HTTP and WebSocket

FastAPI HTTP routes read `Authorization: Bearer <token>`. WebSocket handlers first use the same authorization header and fall back to `access_token` query parameter. The adapter injects an internal `Request` or `WebSocket` parameter into the FastAPI signature, authenticates before user handler invocation, and stores `AuthContext` in `ApplicationContext`.

| Condition | HTTP result | WebSocket result |
| --- | --- | --- |
| public route with missing or bad credential | user handler runs | user handler runs |
| protected route missing credential | 401 | close code 1008 |
| authentication failure | 401 | close code 1008 |
| authorization DENY | 403 | close code 1008 |
| provider unavailable or metadata conflict | 500 | close code 1011 |

### gRPC

gRPC reads invocation metadata. `authorization: Bearer <token>` becomes a bearer credential. If no bearer metadata exists, the adapter accepts `spakky.auth.context_snapshot` or `x-spakky-auth-context-snapshot` as an `AUTH_CONTEXT_SNAPSHOT` credential. When a credential exists but no authentication provider is registered, the helper raises gRPC `Unavailable`.

The boundary value in `AuthInvocation` is `grpc`, and operation is the registered RPC operation string.

### Typer CLI

Typer commands get an auth option automatically when no existing `--auth-token` option is present. The adapter reads `--auth-token` first and `SPAKKY_AUTH_TOKEN` second. stdin is not an auth carrier. Before each command, it clears context-scoped state to avoid cross-command leakage, authenticates the bearer token when present, and seeds `AuthContext`.

| Decision | Exit code | Output |
| --- | --- | --- |
| `CHALLENGE` | 2 | reason code and optional reason |
| `DENY` | 3 | reason code and optional reason |
| `ERROR` | 1 | reason code and optional reason |

Commands without auth decorator are allowed even when no provider exists.

### spakky-task direct execution

Direct in-process task execution keeps the current request/context scope. It does not clear `ApplicationContext`, does not require a snapshot, and does not pass `AuthContext` as a method argument. Auth decorator metadata is copied onto task routes so queue adapters can enforce it later.

### Celery

Celery dispatch aspects inject signed snapshot metadata into task headers when `AuthSnapshotPropagationConfig(enabled=True)` is registered and the current context contains an `AuthContext`. The header key is `spakky.auth.context_snapshot`. If propagation is enabled and a context exists but no signer is available, dispatch fails loudly.

Protected worker tasks verify the snapshot, seed `AuthContext`, then evaluate task metadata before user code. Missing, invalid, or expired snapshots are `CHALLENGE`; verifier unavailable is `ERROR` and is retryable by `is_retryable_auth_failure()`.

### spakky-event propagation

`AuthContextSnapshotHeaderInjector` removes raw bearer `Authorization` headers from outbound event headers even when propagation is disabled. When propagation is enabled and an `AuthContext` exists, it signs and writes `spakky.auth.context_snapshot`. Missing application context, invalid context value, or missing signer are loud errors; missing `AuthContext` in a public flow simply skips the snapshot.

### RabbitMQ

RabbitMQ consumers convert AMQP headers to string values, store them in a message-local context, clear `ApplicationContext`, verify a signed snapshot, and seed `AuthContext` before the integration event handler runs. Supported keys are `spakky.auth.context_snapshot` and `x-spakky-auth-context-snapshot`; the metadata key wins when both are present.

Protected handler auth failures are mapped to configured message actions:

| Decision state | Default action |
| --- | --- |
| `CHALLENGE` | `ack` |
| `DENY` | `ack` |
| `ERROR` | `nack_requeue` |

The actions are configured by RabbitMQ settings `auth_challenge_action`, `auth_deny_action`, and `auth_error_action`.

### Kafka

Kafka consumers decode message headers, clear `ApplicationContext`, and pass headers only to auth-aware handler wrappers. Protected handlers verify `x-spakky-auth-context-snapshot` first and `spakky.auth.context_snapshot` as fallback, case-insensitively. Missing, invalid, or expired snapshot returns a non-ALLOW decision and the handler is skipped. Snapshot verifier unavailable is propagated as an error so the consumer can treat it as retryable infrastructure failure.

Public Kafka handlers preserve previous no-auth behavior and run without a snapshot or verifier.

### Saga

`AbstractSagaData` carries `auth_context_snapshot`. Protected saga steps and protected compensation callbacks verify that snapshot before execution and then evaluate the same decorator requirement kinds as normal auth boundaries. If a step returns replacement saga data without a snapshot, the engine preserves the current snapshot; if the returned data includes a new snapshot, the engine keeps the new one.

Missing, invalid, and expired snapshots fail the protected step as `CHALLENGE`. Provider unavailable or missing requirement provider fails as `ERROR`. Saga history records the step failure and normal saga error strategy handling continues.

---

## R03 final conformance matrix

R03 runs after R04 and is the final technical gate for the authentication and authorization milestone. The matrix below is the cross-package reference for the implemented boundary behavior.

| Boundary | Public call without decorator | Protected success | `CHALLENGE` path | `DENY` path | `ERROR` / provider unavailable | Context ordering | Snapshot path | Startup validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FastAPI HTTP | Allowed; handler runs without a credential | Bearer credential seeds `AuthContext`; requirement decorators evaluate before handler | 401 for missing, invalid, or expired inbound bearer credential | 403 for authorization denial | 500 for auth provider unavailable or metadata conflict | Existing request scope is cleared before `AuthContext` is stored | Not propagated by HTTP; bearer is inbound only | Protected route requires exactly one matching provider capability |
| FastAPI WebSocket | Allowed; handler runs without a credential | Header bearer or `access_token` query token seeds `AuthContext` before handler | close code 1008 for missing, invalid, or expired credential | close code 1008 | close code 1011 | WebSocket wrapper clears scope before seed | Not propagated by WebSocket; bearer is inbound only | Protected socket handler requires exactly one matching provider capability |
| gRPC unary | Allowed when no auth metadata is present | Metadata bearer or signed snapshot seeds `AuthContext` before unary handler | gRPC unauthenticated for missing, invalid, or expired credential/snapshot | gRPC permission denied | gRPC unavailable/internal for provider unavailable or metadata conflict | Interceptor clears request scope before seed | Accepts `spakky.auth.context_snapshot` and `x-spakky-auth-context-snapshot` | Protected RPC requires exactly one matching provider capability |
| gRPC stream | Allowed when no auth metadata is present | Stream interceptor seeds `AuthContext` before user stream handling | gRPC unauthenticated for missing, invalid, or expired credential/snapshot | gRPC permission denied | gRPC unavailable/internal for provider unavailable or metadata conflict | Interceptor clears request scope before seed | Accepts metadata/header snapshot credentials | Protected stream requires exactly one matching provider capability |
| Typer | Allowed even without provider or token | `--auth-token` or `SPAKKY_AUTH_TOKEN` seeds `AuthContext` before command | exit 2 for missing, invalid, or expired bearer credential | exit 3 | exit 1 | CLI command clears context before seed | No snapshot propagation; stdin is not an auth carrier | Protected command requires exactly one matching provider capability |
| spakky-task direct | Allowed in current request/context scope | Task metadata is evaluated against existing `AuthContext` | Protected direct call without context fails closed as `CHALLENGE` | Requirement denial fails closed as `DENY` | Provider unavailable or missing requirement provider is `ERROR` | Direct execution does not clear the current scope | Queue adapters receive copied metadata; direct execution does not require a snapshot | Protected task metadata requires exactly one matching provider capability |
| Celery | Public task runs without snapshot | Worker verifies signed snapshot, seeds `AuthContext`, then evaluates task metadata | Missing, invalid, or expired snapshot is `CHALLENGE` | Requirement denial is `DENY` | Verifier unavailable is retryable `ERROR` | Worker clears scope before snapshot seed | Dispatch writes `spakky.auth.context_snapshot`; worker verifies it | Enabled propagation requires exactly one signer and one verifier provider |
| spakky-event propagation | Public event send can skip snapshot when no `AuthContext` exists | Outbound event includes signed `AuthContextSnapshot` metadata when enabled | Downstream protected consumer maps missing, invalid, or expired snapshot to `CHALLENGE` | Downstream handler denial is `DENY` | Missing signer for enabled propagation or invalid context is `ERROR` | Outbound injector removes raw bearer before writing snapshot | Uses `spakky.auth.context_snapshot`; raw bearer is never propagated | Enabled propagation requires exactly one snapshot signer and verifier |
| RabbitMQ | Public handler preserves previous no-auth behavior | Consumer verifies snapshot and seeds `AuthContext` before handler | Missing, invalid, or expired snapshot maps to configured challenge action, default `ack` | Default `ack` | Default `nack_requeue` | Message-local context and application context are cleared before seed | Metadata key wins over `x-spakky-auth-context-snapshot` when both exist | Protected handler and enabled propagation require exactly one provider per capability |
| Kafka | Public handler preserves previous no-auth behavior | Consumer verifies snapshot and seeds `AuthContext` before handler | Missing, invalid, or expired snapshot skips protected handler with non-ALLOW decision | Protected handler skipped with non-ALLOW decision | Provider unavailable is propagated as retryable infrastructure error | Consumer clears application context before auth-aware wrapper runs | `x-spakky-auth-context-snapshot` wins, `spakky.auth.context_snapshot` is fallback | Protected handler and enabled propagation require exactly one provider per capability |
| Saga | Public step/compensation follows normal saga flow | Step verifies snapshot, seeds `AuthContext`, and evaluates decorators | Missing, invalid, or expired snapshot fails protected step as `CHALLENGE` | Requirement denial fails step as `DENY` | Provider unavailable or missing requirement provider fails step as `ERROR` | Step wrapper seeds before action or compensation callback | `AbstractSagaData.auth_context_snapshot` is preserved across replacement data unless explicitly replaced | Protected step and snapshot propagation require exactly one provider per capability |

Provider count validation is feature-local: zero providers or two or more providers for a required capability fail startup when protected metadata or enabled snapshot propagation needs that capability. Zero providers remain valid only when the application has no protected auth usage and no enabled snapshot propagation.

## R03 provider matrix

| Provider | Valid path | Invalid path | Unavailable path | Evidence surface |
| --- | --- | --- | --- | --- |
| OIDC | Valid bearer JWT maps selected safe claims to `AuthContext` | malformed token, invalid signature, issuer/audience/`azp`/time claim failure, or JWKS key miss returns `CHALLENGE / INVALID_CREDENTIAL` | discovery or JWKS fetch failure returns `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-oidc` provider tests and FastAPI/gRPC/Typer boundary tests |
| Policy | Matching allow returns explainable allow evidence | explicit deny wins; no matching allow returns deny evidence | malformed or unavailable policy document/provider returns `ERROR` through the auth port | `plugins/spakky-policy` evaluator/provider tests |
| OpenFGA | Check response allowed maps to `ALLOW` | check response denied maps to `DENY` | OpenFGA client/service unavailable maps to `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-openfga` provider tests |
| Cryptography | Snapshot sign/verify, hash, HMAC, and password verify success return provider-native success values | invalid signature, malformed envelope, expired snapshot, and password verification failure return `CHALLENGE / INVALID_CREDENTIAL` where exposed through auth ports | signer/verifier/password provider unavailable maps to `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-cryptography` auth provider tests |

R03 evidence commands:

```bash
uv run mkdocs build --strict
```

Run the legacy reference-search command from [인증/인가 전환 가이드](auth-migration.md). It must match only that migration guide. Matches in source, package READMEs, API reference pages, planning docs, root docs, pyproject files, or examples fail the R03 gate.

---

## Diagnostics

Startup validation runs after plugin loading and scan, before service start.

- Any protected metadata requires exactly one `AUTHENTICATION` provider.
- `@require_permission`, `@require_role`, `@require_scope`, `@require_policy`, and `@require_relation` require exactly one matching provider capability.
- Enabled `AuthSnapshotPropagationConfig` requires exactly one `SNAPSHOT_SIGN` and one `SNAPSHOT_VERIFY` provider.
- If no protected usage and no enabled snapshot propagation config exist, provider absence is not fatal.

Provider count 0 or 2+ raises `AuthStartupCapabilityValidationError` and emits `auth.capability.validation.error` startup diagnostic detail. Runtime non-ALLOW decisions are preserved on `AuthRequirementDeniedError.decision` so adapters can map `CHALLENGE`, `DENY`, and `ERROR` to transport-specific responses.

## Migration

See [인증/인가 전환 가이드](auth-migration.md) for migration from the removed legacy security package and the final grep allowlist used by the R03 conformance gate.
