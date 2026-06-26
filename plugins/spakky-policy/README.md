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


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.fastapi.PLUGIN_NAME,
            spakky.plugins.policy.PLUGIN_NAME,
        }
    )
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

## Policy 문서 구조

정책 문서는 YAML, TOML, JSON을 지원하며 다음 top-level collection을 typed canonical model로 변환합니다.

| 필드 | 의미 |
| --- | --- |
| `version` | policy document schema version 문자열 |
| `metadata` | `name`, optional `description`, `labels` |
| `subjects` | subject ref와 역할, scope, permission, claim, tenant binding |
| `resources` | resource ref와 optional tenant |
| `actions` | action ref |
| `permissions` | resource/action 묶음을 가진 named permission |
| `roles` | permission 묶음을 가진 named role |
| `scopes` | permission 묶음을 가진 named scope |
| `policies` | statement 목록을 가진 named policy |
| `conditions` | 재사용 가능한 atomic/composite condition |

최소 YAML 예:

```yaml
version: "1"
metadata:
  name: article-policy
subjects:
  - ref: user:alice
    roles: [role:editor]
resources:
  - ref: article:1
actions:
  - ref: article:read
permissions:
  - ref: permission:article-read
    resources: [article:1]
    actions: [article:read]
roles:
  - ref: role:editor
    permissions: [permission:article-read]
policies:
  - ref: policy:read-article
    statements:
      - ref: allow-editor
        effect: allow
        roles: [role:editor]
        resources: [article:1]
        actions: [article:read]
```

## 플러그인 등록

Base plugin entry point는 `SpakkyPolicyConfig`, `spakky_policy_document`, `SpakkyPolicyAuthProvider`를 등록하고 `IAuthorizationPolicyEvaluator`, `IPermissionChecker`, `IRoleChecker`, `IScopeChecker`를 provider에 binding합니다. Auth feature contribution entry point는 `spakky.contributions.spakky.auth` group에 policy/permission/role/scope capability metadata를 등록합니다.

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT
