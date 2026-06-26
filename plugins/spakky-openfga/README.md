# spakky-openfga

> `spakky-openfga`는 Spakky Auth의 relation 기반 인가를 OpenFGA check로 수행하는 provider 플러그인입니다.
> `@require_relation` metadata를 OpenFGA tuple model과 store/client 설정에 연결합니다.

## Auth Provider Capability

플러그인은 다음 capability를 구현하는 `OpenFgaAuthProvider`를 등록합니다.

- `AuthCapability.RELATION_CHECK`
- `AuthCapability.POLICY_EVALUATION`

`RelationCheckRequest.relation`과 `AuthorizationRequest.action`은 OpenFGA relation으로
매핑됩니다. `AuthContext.subject.id`는 OpenFGA user로 매핑되고, resource/tenant canonical
ref는 OpenFGA object 문자열로 매핑됩니다.

## 설치

```bash
pip install spakky-auth spakky-openfga
```

## 설정

`OpenFgaConfig`는 settings Pod로 등록되며 `SPAKKY_OPENFGA_*` 환경변수를 읽습니다.
OpenFGA API URL, store id, optional authorization model id, principal type,
tenant/object 매핑 설정을 담습니다. 기본적으로 type prefix가 없는 subject id는
`user:<subject>`로 매핑되고, tenant ref는 `<tenant>/<resource>` 형태로 object ref 앞에
붙습니다.

주요 설정:

| 환경변수 | 의미 | 기본값 |
| --- | --- | --- |
| `SPAKKY_OPENFGA_API_URL` | OpenFGA API URL | `http://localhost:8080` |
| `SPAKKY_OPENFGA_STORE_ID` | check request에 사용할 store id | `""` |
| `SPAKKY_OPENFGA_AUTHORIZATION_MODEL_ID` | optional authorization model id | 미설정 |
| `SPAKKY_OPENFGA_PRINCIPAL_TYPE` | type prefix 없는 subject id에 붙일 user type | `user` |
| `SPAKKY_OPENFGA_TENANT_SEPARATOR` | tenant ref와 resource ref를 결합할 separator | `/` |
| `SPAKKY_OPENFGA_INCLUDE_TENANT_IN_OBJECT` | tenant ref를 object string 앞에 붙일지 여부 | `true` |
| `SPAKKY_OPENFGA_RELATION_CHECK_AVAILABLE` | relation check provider 가용성 | `true` |

## 사용법

```python
import spakky.auth
import spakky.plugins.openfga
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.openfga.PLUGIN_NAME,
        }
    )
    .start()
)
```

Base plugin entry point는 `OpenFgaConfig`, `OpenFgaSdkCheckClient`, `OpenFgaAuthProvider`를 등록하고 `IRelationChecker`, `IAuthorizationPolicyEvaluator`를 provider에 binding합니다. Auth feature contribution entry point는 `spakky.contributions.spakky.auth` group에 `RELATION_CHECK`, `POLICY_EVALUATION` capability metadata를 등록합니다.

## 범위 밖

이 패키지는 tuple write, authorization model migration, admin CLI/API, list resources,
data/query filtering, tuple/model management surface를 제공하지 않습니다.

Provider를 사용할 수 없는 상태는 `AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE`
reason code를 가진 `ERROR` authorization decision으로 매핑됩니다.

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

MIT License
