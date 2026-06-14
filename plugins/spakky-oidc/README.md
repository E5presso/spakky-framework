# spakky-oidc

> `spakky-oidc`는 OIDC/OAuth bearer JWT credential을 검증하는 인증 provider 플러그인입니다.
> 검증된 claim을 `spakky.auth.AuthContext`로 매핑하고 bearer authentication capability를 제공합니다.

이 플러그인은 `spakky.contributions.spakky.auth` entry point로
`AuthCapability.AUTHENTICATION`을 제공합니다. Browser login, callback, session,
refresh, logout route는 포함하지 않습니다. FastAPI, gRPC, Typer 같은 inbound adapter가
경계에서 bearer credential을 읽고 provider-neutral `IAuthenticationProvider` port로
전달합니다.

## 제공 기능

- `issuer/.well-known/openid-configuration` 또는 명시적 discovery URL 기반 OIDC discovery
- `kid` 기반 JWKS key 선택과 RS256 signature 검증
- `issuer`, `audience`, `azp`, `exp`, `nbf`, `iat`, clock skew 검증
- `sub`, 표시 이름, tenant, role, scope, 선택된 safe claim의 `AuthContext` 매핑
- raw bearer token을 `AuthContext.claims`, `metadata`, `credential_carrier`에 남기지 않음

## 설치

```bash
pip install spakky-auth spakky-oidc spakky-fastapi
```

## 사용법

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

`OidcProviderConfig`는 Spakky `@Configuration` Pod입니다.
`SPAKKY_OIDC_ISSUER`, `SPAKKY_OIDC_AUDIENCE`, `SPAKKY_OIDC_CLIENT_ID`와
`SPAKKY_OIDC_ROLES_CLAIM`, `SPAKKY_OIDC_SCOPES_CLAIM`,
`SPAKKY_OIDC_TENANT_CLAIM`, `SPAKKY_OIDC_DISPLAY_NAME_CLAIM` 같은 claim 매핑
환경변수로 설정합니다. 기본 scope claim은 표준 공백 구분 `scope` 문자열을 허용하며,
role과 custom scope claim은 문자열 배열도 허용합니다.

Inbound adapter는 boundary에서 bearer credential을 관찰하고 provider-neutral auth port를
호출해 `AuthContext`를 저장합니다. 애플리케이션 코드는 provider를 직접 호출하지 않고
`spakky-auth` decorator로 요구사항을 선언합니다.

## 라이선스

MIT
