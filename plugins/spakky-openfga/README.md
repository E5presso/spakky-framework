# spakky-openfga

`spakky-openfga`는 Spakky Auth의 relation 기반 인가를 위해 OpenFGA check만 수행하는
authorization provider 플러그인입니다.

## Auth Provider Capability

플러그인은 다음 capability를 구현하는 `OpenFgaAuthProvider`를 등록합니다.

- `AuthCapability.RELATION_CHECK`
- `AuthCapability.POLICY_EVALUATION`

`RelationCheckRequest.relation`과 `AuthorizationRequest.action`은 OpenFGA relation으로
매핑됩니다. `AuthContext.subject.id`는 OpenFGA user로 매핑되고, resource/tenant canonical
ref는 OpenFGA object 문자열로 매핑됩니다.

## 설정

`OpenFgaConfig`는 settings Pod로 등록되며 `SPAKKY_OPENFGA_*` 환경변수를 읽습니다.
OpenFGA API URL, store id, optional authorization model id, principal type,
tenant/object 매핑 설정을 담습니다. 기본적으로 type prefix가 없는 subject id는
`user:<subject>`로 매핑되고, tenant ref는 `<tenant>/<resource>` 형태로 object ref 앞에
붙습니다.

주요 설정:

- `SPAKKY_OPENFGA_API_URL`
- `SPAKKY_OPENFGA_STORE_ID`
- `SPAKKY_OPENFGA_AUTHORIZATION_MODEL_ID`
- `SPAKKY_OPENFGA_PRINCIPAL_TYPE`
- `SPAKKY_OPENFGA_INCLUDE_TENANT_IN_OBJECT`

## 범위 밖

이 패키지는 tuple write, authorization model migration, admin CLI/API, list resources,
data/query filtering, tuple/model management surface를 제공하지 않습니다.

Provider를 사용할 수 없는 상태는 `AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE`
reason code를 가진 `ERROR` authorization decision으로 매핑됩니다.
