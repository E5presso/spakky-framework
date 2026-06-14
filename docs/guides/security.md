# 인증/인가

> `spakky-auth`와 provider plugin으로 인증, 인가, snapshot 전파를 구성하는 입문 가이드입니다.

Spakky의 인증/인가는 세 부분으로 나뉩니다. `spakky-auth`는 공통 계약을 정의하고, provider 플러그인은 실제 검증을 맡고, FastAPI·gRPC·Typer·메시지 브로커 어댑터는 사용자 코드가 실행되기 전에 `AuthContext`를 채웁니다.

핵심 규칙은 단순합니다.

- 인증 데코레이터가 없으면 공개 경계입니다.
- `@protected`, `@require_scope`, `@require_role`, `@require_permission`, `@require_policy`, `@require_relation`이 붙으면 실패 시 닫히는 경계가 됩니다.
- Bearer token은 HTTP, WebSocket, gRPC, CLI처럼 사용자가 직접 들어오는 경계에서만 읽습니다.
- task, broker, event, saga로 이어지는 내부 전파에는 token 대신 서명된 `AuthContextSnapshot`을 사용합니다.

---

## 패키지 구성

필요한 기능에 맞춰 core 패키지와 provider 플러그인을 함께 설치합니다.

```bash
pip install spakky-auth spakky-oidc spakky-policy spakky-openfga spakky-cryptography
```

애플리케이션은 auth core plugin과 실제 provider plugin을 함께 로드합니다. Provider contribution은 `spakky.contributions.spakky.auth` entry point로 자신이 제공하는 기능을 선언합니다. 시작 시점에는 보호된 경계와 snapshot 전파가 요구하는 기능을 정확히 하나의 provider가 제공하는지 검사합니다.

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

관계 기반 인가가 필요하면 `spakky-openfga`를 추가합니다. 서명된 snapshot 전파나 password hash/verify가 필요하면 `spakky-cryptography`를 함께 사용합니다.

---

## Decorator

Decorator는 class 또는 method에 인증/인가 요구사항을 붙입니다. 메서드가 `AuthContext`를 직접 인자로 받을 필요는 없습니다. 어댑터가 사용자 코드 호출 전에 `ApplicationContext`에 context를 저장하고, `AuthorizationAspect` 또는 adapter wrapper가 요구사항을 평가합니다.

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

Class-level 요구사항과 method-level 요구사항은 모두 만족해야 합니다. 같은 요구사항은 중복 제거됩니다. `@public_access`와 보호 요구사항이 같은 경계에 함께 있으면 `ConflictingAuthMetadataError`로 시작 또는 호출이 실패합니다.

| Decorator | 필요한 provider 기능 |
| --- | --- |
| `@protected` | `AUTHENTICATION` |
| `@require_scope("documents:read")` | `SCOPE_CHECK` |
| `@require_role("role:admin")` | `ROLE_CHECK` |
| `@require_permission("documents:read", resource="document:1")` | `PERMISSION_CHECK` |
| `@require_policy("document:1", "read")` | `POLICY_EVALUATION` |
| `@require_relation("owner", resource="document:1")` | `RELATION_CHECK` |

OR/ANY 같은 복합 조건은 decorator 조합으로 표현하지 않습니다. 그런 규칙은 `spakky-policy`의 named policy로 옮기세요.

---

## Provider

### OIDC

`spakky-oidc`는 Bearer JWT를 검증하고 `AuthContext`로 매핑하는 authentication provider입니다. 이 플러그인은 inbound bearer token 인증에 집중합니다. Browser login, callback, session, refresh, logout route는 애플리케이션이나 별도 서비스에서 다룹니다.

```python
from fastapi import FastAPI
from spakky.auth import protected, require_scope
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.fastapi.routes import get
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController
import spakky.auth
import spakky.plugins.fastapi
import spakky.plugins.oidc


@ApiController("/documents")
class DocumentController:
    @get("/{document_id}")
    @require_scope("documents:read")
    @protected
    def read(self, document_id: str) -> dict[str, str]:
        return {"id": document_id}


@Pod()
def get_api() -> FastAPI:
    return FastAPI()


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.fastapi.PLUGIN_NAME,
            spakky.plugins.oidc.PLUGIN_NAME,
        }
    )
    .add(get_api)
    .add(DocumentController)
    .start()
)
api = app.container.get(FastAPI)
```

OIDC provider는 discovery document와 JWKS를 읽고, `kid` key selection, RS256 signature, issuer, audience, `azp`, `exp`, `nbf`, `iat`, clock skew를 검증합니다. `sub`, display name, tenant, roles, scopes, selected safe claims만 `AuthContext`에 남기며 raw bearer token은 claims, metadata, credential carrier에 보존하지 않습니다.
FastAPI/gRPC/Typer 같은 inbound adapter가 boundary에서 bearer credential을 읽고 provider-neutral auth port를 호출한 뒤 `AuthContext`를 저장하므로, 애플리케이션 코드는 provider를 직접 호출하지 않고 decorator로 요구사항을 선언합니다.

실패는 다음 decision으로 정규화됩니다.

| 실패 | Decision |
| --- | --- |
| bearer credential 없음 | `CHALLENGE / MISSING_CREDENTIAL` |
| malformed credential 또는 invalid token | `CHALLENGE / INVALID_CREDENTIAL` |
| JWKS key selection failure | `CHALLENGE / INVALID_CREDENTIAL` |
| discovery/provider 비가용 | `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` |

### Policy

`spakky-policy`는 YAML, TOML, JSON policy document를 typed model로 로드하고 RBAC, PBAC, ABAC-style rule을 평가합니다. Policy UI, generic policy API, MCP/tool authorization, authorized data filtering은 범위 밖입니다.

```python
from fastapi import FastAPI
from spakky.auth import protected, require_policy
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.fastapi.routes import get
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController
import spakky.auth
import spakky.plugins.fastapi
import spakky.plugins.policy


@ApiController("/documents")
class DocumentController:
    @get("/{document_id}")
    @require_policy(resource="document:1", action="read")
    @protected
    def read(self, document_id: str) -> dict[str, str]:
        return {"id": document_id}


@Pod()
def get_api() -> FastAPI:
    return FastAPI()


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.fastapi.PLUGIN_NAME,
            spakky.plugins.policy.PLUGIN_NAME,
        }
    )
    .add(get_api)
    .add(DocumentController)
    .start()
)
api = app.container.get(FastAPI)
```

`SPAKKY_POLICY_DOCUMENT_PATH`가 YAML, TOML, JSON policy document를 가리키면
plugin이 해당 문서를 DI-managed `PolicyDocument`로 로드합니다.

명시적 deny는 matching allow보다 우선합니다. Matching allow가 없으면 default deny evidence를
반환합니다. Condition은 `all`, `any`, `not` composition과 `equals`, `not_equals`, `in`,
`contains`, `exists` operator를 지원합니다.

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

Provider를 호출할 수 없으면 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` decision을 반환합니다. 빈 canonical reference처럼 OpenFGA user/object/relation으로 매핑할 수 없는 값은 `ERROR / INTERNAL_ERROR`로 반환됩니다.

### Cryptography

`spakky-cryptography`는 기존 crypto utility와 auth provider 기능을 함께 제공합니다.

- `SNAPSHOT_SIGN`, `SNAPSHOT_VERIFY`: `AuthContextSnapshot` HMAC envelope 서명/검증
- `PASSWORD_HASH`, `PASSWORD_VERIFY`: password hash/verify port
- `Key`, `Base64Encoder`, `Hash`, `HMAC`, `Aes`, `Gcm`, `Rsa`, 유지되는 password encoder

```python
from spakky.auth import AuthSnapshotPropagationConfig, IPasswordHasher
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
import spakky.auth
import spakky.plugins.cryptography


@Pod()
def auth_snapshot_propagation_config() -> AuthSnapshotPropagationConfig:
    return AuthSnapshotPropagationConfig(enabled=True)


@UseCase()
class RegisterPassword:
    def __init__(self, hasher: IPasswordHasher) -> None:
        self._hasher = hasher

    def execute(self, password: str) -> str:
        return self._hasher.hash_password(password)


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.cryptography.PLUGIN_NAME,
        }
    )
    .add(auth_snapshot_propagation_config)
    .add(RegisterPassword)
    .start()
)
```

`SPAKKY_CRYPTOGRAPHY_SNAPSHOT_KEY`에는 url-safe Base64 HMAC key를 설정할 수 있습니다.
Snapshot envelope이 없거나 잘못되었거나 만료되면 `CHALLENGE`로 매핑됩니다. Verification provider를 사용할 수 없으면 `ERROR`가 됩니다. Password verification failure는 `CHALLENGE / INVALID_CREDENTIAL`, password provider 비가용은 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE`로 매핑됩니다.

---

## 실행 경계

각 integration은 같은 auth contract를 transport에 맞게 적용합니다.

| 경계 | 인증 입력 | 결과 |
| --- | --- | --- |
| FastAPI HTTP/WebSocket | Bearer token | `AuthContext` 저장 후 handler 실행 |
| gRPC | Bearer metadata 또는 signed snapshot | RPC handler 실행 전 인증/인가 |
| Typer | `--auth-token` 또는 `SPAKKY_AUTH_TOKEN` | command 실행 전 인증/인가 |
| Celery/RabbitMQ/Kafka | signed `AuthContextSnapshot` | worker/consumer handler 실행 전 검증 |
| Saga | `AbstractSagaData.auth_context_snapshot` | 보호된 step과 compensation callback 실행 전 검증 |

Transport별 상태 코드, message ack 정책, startup validation 기준은 [인증/인가 심화](security-advanced.md)에 분리해 두었습니다. 제거된 legacy security package에서 옮기는 방법은 [인증/인가 전환 가이드](auth-migration.md)를 참고하세요.
