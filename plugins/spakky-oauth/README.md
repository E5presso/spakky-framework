# spakky-oauth

> `spakky-oauth`는 application이 사용자를 대신해 외부 API를 부를 때 쓰는 OAuth 2.0 client 플러그인입니다.
> Authorization code + PKCE로 token을 받고, 만료 전에 갱신하고, 로그아웃 시 폐기합니다.

`spakky-oidc`와 방향이 반대입니다. `spakky-oidc`는 들어오는 bearer token을 검증하고,
`spakky-oauth`는 나가는 호출에 쓸 token을 얻어 보관합니다.

## 제공 기능

- Authorization code flow 시작: `state`, PKCE `S256` challenge, `openid` scope가 있으면 `nonce` 생성
- Callback code 교환과 token 저장
- 만료 `refresh_leeway_seconds` 전 갱신, refresh token 회전 반영
- 같은 주체의 동시 갱신을 하나로 묶는 process-local 잠금
- 다른 instance가 먼저 회전해 저장한 token 재사용 (best-effort; 분산 잠금은 아님)
- Revocation endpoint 호출과 local token 삭제
- Confidential client 인증(`client_secret_basic`, `client_secret_post`)
- 애플리케이션이 직접 저장한 token의 갱신(`refresh_tokens`)과 RFC 7009 폐기(`revoke_token`)
- 오류에 HTTP 상태와 OAuth `error` 값(`OAuthTokenEndpointError.status_code`, `.error`)

## 포함하지 않는 것

- 로그인·callback HTTP route. Application의 inbound adapter(FastAPI 등)가 `OAuthClient`를 호출합니다.
- ID token 서명·claim 검증. `OAuthAuthorizationResult`가 `tokens.id_token`과 `nonce`를 돌려주므로 application이 검증합니다.
- `private_key_jwt` 등 secret 외의 client 인증, device code, client credentials grant.
- 여러 process 사이의 분산 잠금. 저장소 구현이 필요하면 직접 제공합니다.

## 설치

```bash
pip install spakky-oauth
```

## 구성

`OAuthConfig`는 `SPAKKY_OAUTH__` prefix의 환경 변수에서 읽습니다.

```bash
export SPAKKY_OAUTH__CLIENTS='{
  "example": {
    "authorization_endpoint": "https://auth.example.test/authorize",
    "token_endpoint": "https://auth.example.test/token",
    "revocation_endpoint": "https://auth.example.test/revoke",
    "client_id": "my-app",
    "scopes": ["openid", "offline_access"],
    "token_parameters": {"resource": "https://api.example.test"}
  }
}'
```

### `OAuthConfig`

| Field | 기본값 | 책임 |
|-------|--------|------|
| `clients` | `{}` | 이름별 `OAuthClientRegistration` |
| `http_timeout_seconds` | `20.0` | token·revocation 요청 timeout |
| `refresh_leeway_seconds` | `90.0` | 만료 이만큼 전에 갱신 |
| `authorization_ttl_seconds` | `600.0` | 시작한 authorization이 callback을 기다리는 시간 |

### `OAuthClientRegistration`

| Field | 기본값 | 책임 |
|-------|--------|------|
| `authorization_endpoint` | 필수 | 사용자를 보낼 authorization URL |
| `token_endpoint` | 필수 | code 교환과 refresh endpoint |
| `revocation_endpoint` | `None` | 없으면 `revoke()`는 local token만 삭제 |
| `client_id` | 필수 | client id |
| `scopes` | `()` | 요청할 scope |
| `authorization_parameters` | `{}` | authorization 요청에 더할 parameter |
| `token_parameters` | `{}` | code 교환과 refresh 요청에 더할 parameter |
| `token_endpoint_auth_method` | `none` | token·revocation 요청의 client 인증. `none`, `client_secret_basic`, `client_secret_post` |
| `client_secret` | `None` | confidential client의 secret(`SecretStr`). `client_secret_*` 방식에서만, 그때는 반드시 지정 |

Endpoint는 `https`여야 하며 loopback host에 한해 `http`를 허용합니다. 추가 parameter는
`client_id`, `state`, `code_verifier` 같은 protocol field를 덮어쓸 수 없습니다.

## 저장소 등록

Plugin은 `OAuthConfig`와 `OAuthClient`만 등록합니다. Token과 authorization state 저장소는
application이 Pod로 등록합니다. 개발과 테스트에는 in-memory 구현을 쓸 수 있습니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.oauth.store import (
    InMemoryOAuthAuthorizationStateStore,
    InMemoryOAuthTokenStore,
)


@Pod()
class DevTokenStore(InMemoryOAuthTokenStore): ...


@Pod()
class DevStateStore(InMemoryOAuthAuthorizationStateStore): ...
```

운영에서는 `IOAuthTokenStore`와 `IOAuthAuthorizationStateStore`를 database나 cache로 구현합니다.
`InMemoryOAuthAuthorizationStateStore(clock=None)`은 `save()`와 `take()` 때마다 `expires_at`이 지난
authorization을 지웁니다. 시각은 넘긴 `IOAuthClock`(기본 `SystemOAuthClock`)으로 판단합니다. In-memory
구현은 process가 재시작하면 내용을 잃고 callback이 시작한 process로 와야 하므로 운영에 쓰지 않습니다.

`OAuthTokenSet`과 `OAuthPendingAuthorization`의 token과 `code_verifier`는 `SecretStr`입니다.
`model_dump_json()`은 이 값을 `**********`로 바꾸므로 그대로 저장하면 token을 잃습니다.
저장소 구현은 `get_secret_value()`로 값을 꺼내 직접 직렬화하고, 암호화도 책임집니다.

## Confidential client

Client secret을 받은 registration은 `token_endpoint_auth_method`와 `client_secret`을 함께 지정합니다.
두 방식은 RFC 6749 section 2.3.1을 따릅니다.

| `token_endpoint_auth_method` | 요청에 싣는 것 |
| --- | --- |
| `none` (기본) | form의 `client_id` |
| `client_secret_basic` | `Authorization: Basic` header. `client_id`와 secret을 각각 form-urlencode한 뒤 `:`로 이어 base64로 인코딩합니다. form에는 `client_id`를 넣지 않습니다. |
| `client_secret_post` | form의 `client_id`와 `client_secret` |

이 인증은 code 교환, refresh, revocation 요청 모두에 붙습니다. `client_secret`은 `SecretStr`이라
`repr()`, 로그, `model_dump()`에 값이 나오지 않습니다. Secret 없이 `client_secret_*`을 고르거나,
`none`인데 secret을 주거나, `token_parameters`에 `client_secret`을 넣으면 구성 단계에서 거절합니다.

```bash
export SPAKKY_OAUTH__CLIENTS='{
  "calendar": {
    "authorization_endpoint": "https://auth.example.test/authorize",
    "token_endpoint": "https://auth.example.test/token",
    "revocation_endpoint": "https://auth.example.test/revoke",
    "client_id": "calendar-sync",
    "token_endpoint_auth_method": "client_secret_basic",
    "client_secret": "<secret>"
  }
}'
```

## 직접 저장한 token의 갱신과 폐기

Token을 플러그인의 `IOAuthTokenStore`가 아니라 애플리케이션의 aggregate에 저장하는 경우,
아래 두 메서드는 저장소를 읽지도 쓰지도 않고 받은 token으로만 일합니다. Registration의 client 인증이 그대로 붙습니다.

```python
from pydantic import SecretStr

from spakky.plugins.oauth.client import OAuthClient
from spakky.plugins.oauth.error import (
    OAuthAuthorizationRequiredError,
    OAuthTokenEndpointError,
)
from spakky.plugins.oauth.token import OAuthTokenTypeHint


async def renew(oauth: OAuthClient, refresh_token: SecretStr) -> None:
    try:
        tokens = await oauth.refresh_tokens("calendar", refresh_token)
    except OAuthAuthorizationRequiredError:
        ...  # invalid_grant: 사용자가 다시 연결해야 합니다.
    except OAuthTokenEndpointError as error:
        # error.status_code, error.error("invalid_client" 등)로 원인을 구별합니다.
        ...
    else:
        ...  # tokens(OAuthTokenSet)를 aggregate에 암호화해 저장합니다.


async def disconnect(oauth: OAuthClient, refresh_token: SecretStr) -> None:
    await oauth.revoke_token(
        "calendar",
        refresh_token,
        token_type_hint=OAuthTokenTypeHint.REFRESH_TOKEN,
    )
```

| 메서드 | 동작 |
| --- | --- |
| `refresh_tokens(client, refresh_token, *, client_id=None) -> OAuthTokenSet` | refresh grant를 보내 새 token set을 돌려줍니다. Server가 refresh token을 회전하지 않으면 받은 refresh token을, scope를 알려주지 않으면 registration의 `scopes`를 넣습니다. |
| `revoke_token(client, token, *, token_type_hint=None, client_id=None) -> None` | RFC 7009 폐기 요청을 보냅니다. `token_type_hint`(`OAuthTokenTypeHint.ACCESS_TOKEN`/`REFRESH_TOKEN`)가 `None`이면 hint를 보내지 않습니다. |

`client_id`는 token이 registration과 다른 client id로 발급된 경우에만 넘깁니다. `invalid_grant`를 다시 로그인이 필요한 거절로 보는 기준은 `access_token()`과 같습니다. 다만 `refresh_tokens()`는 저장소를 읽지 않으므로, 다른 instance가 먼저 회전시킨 token으로 대신 답하지 않고 항상 오류를 냅니다.

Server가 응답에서 `scope`를 생략하면 RFC 6749 section 6에 따라 원래 grant와 같은 scope라는 뜻이지만, `refresh_tokens()`는 원래 grant를 모르므로 registration의 `scopes`를 넣습니다. 원래 grant가 더 좁았다면 저장해 둔 scope를 그대로 쓰십시오.

| Server 응답 | `refresh_tokens()` | `revoke_token()` |
| --- | --- | --- |
| 200 | `OAuthTokenSet` | 성공 |
| `error="invalid_grant"` | `OAuthAuthorizationRequiredError` | `OAuthRevocationError(status_code, "invalid_grant")` |
| 그 밖의 4xx/5xx | `OAuthTokenEndpointError(status_code, error)` | `OAuthRevocationError(status_code, error)` |
| 연결 실패 | `OAuthTransportError` | `OAuthRevocationError(None, None)` |

`revocation_endpoint`가 없는 registration으로 `revoke_token()`을 부르면 `OAuthRevocationNotSupportedError`입니다.
빈 token이나 빈 `client_id` override는 요청 전에 `OAuthAuthorizationRequestError`입니다.

## 사용법

```python
from spakky.plugins.oauth.client import OAuthClient
from spakky.plugins.oauth.error import OAuthAuthorizationRequiredError


async def login(oauth: OAuthClient, user_id: str) -> str:
    request = await oauth.begin_authorization(
        "example",
        user_id,
        "https://app.example.test/auth/callback",
    )
    return request.url  # 사용자를 이 URL로 redirect


async def callback(oauth: OAuthClient, state: str, code: str) -> None:
    # 먼저 state가 이 브라우저 session에서 시작한 값인지 대조합니다.
    result = await oauth.complete_authorization(state, code)
    # result.tokens.id_token과 result.nonce로 ID token을 검증합니다.


async def call_api(oauth: OAuthClient, user_id: str) -> str:
    try:
        return await oauth.access_token("example", user_id)
    except OAuthAuthorizationRequiredError:
        # 다시 로그인이 필요합니다.
        raise
```

**Callback은 반드시 로그인한 session에 묶습니다.** `begin_authorization()`이 돌려준 `state`를
사용자의 브라우저 session에 저장하고, callback에서 받은 `state`가 그 값과 같은지 확인한 뒤
`complete_authorization()`을 호출합니다. 이 확인이 없으면 공격자가 자기 주체로 시작한 URL을
피해자에게 열게 해 피해자의 token을 공격자 주체 아래 저장할 수 있습니다.

Resource server가 token을 401로 거절하면 그 token을 넘겨 한 번 갱신합니다.
저장된 token이 이미 다른 token으로 바뀌었다면 갱신하지 않고 새 token을 돌려줍니다.

```python
token = await oauth.access_token("example", user_id, rejected_token=token)
```

Sign-in마다 client id를 발급하는 server는 `begin_authorization(..., client_id=...)`와
`complete_authorization(..., client_id=...)`로 실제 client id를 전달합니다. 요청별 추가
parameter는 `begin_authorization(..., parameters={...})`로 넘깁니다.

## 에러

| 에러 | 의미 |
|------|------|
| `OAuthClientNotConfiguredError` | 이름에 해당하는 registration이 없음 |
| `OAuthAuthorizationRequestError` | 요청별 parameter가 protocol field를 덮어쓰거나 `client_id` override가 비어 있음 |
| `OAuthAuthorizationStateError` | callback `state`를 모르거나 이미 썼거나 만료됨 |
| `OAuthAuthorizationRequiredError` | token이 없거나 grant가 거절되어 다시 로그인해야 함 |
| `OAuthTokenEndpointError` | token endpoint가 `invalid_grant`가 아닌 이유로 실패. `status_code`(HTTP 상태)와 `error`(RFC 6749 §5.2 `error`, 본문이 JSON 객체가 아니거나 문자열 `error`가 없으면 `None`)를 가짐 |
| `OAuthTokenResponseError` | token 응답이 사용할 수 있는 bearer token이 아님 |
| `OAuthTransportError` | authorization server에 연결하지 못함 |
| `OAuthRevocationError` | server에 닿지 못했거나 server가 폐기를 확인하지 않음. `status_code`(연결 실패면 `None`)와 `error`를 가짐. `revoke()`에서는 local token을 이미 삭제한 뒤임 |
| `OAuthRevocationNotSupportedError` | `revocation_endpoint`가 없는 registration으로 `revoke_token()`을 부름 |

Token endpoint가 `error="invalid_grant"`로 답한 경우에만 `OAuthAuthorizationRequiredError`를 올립니다.
그 밖의 4xx/5xx는 `OAuthTokenEndpointError`입니다. 두 경우 모두 `access_token()`은 저장된 token을
지우지 않습니다. 다른 instance가 방금 회전해 저장하려는 token을 지우지 않기 위해서입니다.
다시 로그인시키기 전에 저장분을 비우려면 `revoke()`를 호출합니다.

## 라이선스

MIT
