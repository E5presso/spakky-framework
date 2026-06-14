# spakky-policy

> `spakky-policy`는 YAML, TOML, JSON policy document를 typed canonical model로 로드합니다.
> `spakky-auth`의 RBAC, PBAC, ABAC-style 인가 규칙을 provider contribution으로 평가합니다.

## 설치

```bash
pip install spakky-auth spakky-policy spakky-fastapi
```

## 사용법

`SPAKKY_POLICY_DOCUMENT_PATH`가 YAML, TOML, JSON 문서를 가리키면 플러그인이 해당 문서를
DI-managed `PolicyDocument`로 로드합니다. 경로를 설정하지 않으면 비어 있는 policy document를
등록해 인가 요청을 안전하게 거부합니다.

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


@ApiController("/articles")
class ArticleController:
    @get("/{article_id}")
    @require_policy(resource="article:1", action="article:read")
    @protected
    def read(self, article_id: str) -> dict[str, str]:
        return {"id": article_id}


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
    .add(ArticleController)
    .start()
)
api = app.container.get(FastAPI)
```

## Policy 의미

- 명시적 deny statement는 matching allow statement보다 우선합니다.
- matching allow statement가 없으면 default deny evidence를 반환합니다.
- condition은 `all`, `any`, `not` composition과 `equals`, `not_equals`, `in`,
  `contains`, `exists` atomic operator를 지원합니다.
- resource, action, tenant ref는 decorator metadata, `AuthContext`, resolver output,
  또는 provider-neutral `AuthorizationRequest`에서 온 canonical string입니다.
- named policy가 OR/ANY 사용자 표면입니다. MCP/tool authorization, generic policy API,
  policy UI, authorized data filtering은 이 패키지 범위 밖입니다.

## 라이선스

MIT
