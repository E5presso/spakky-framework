# spakky-oauth

> `spakky-oauth`는 application이 사용자를 대신해 외부 API를 부를 때 쓰는 OAuth 2.0 public client 플러그인입니다.
> Authorization code + PKCE로 token을 받고, 만료 전에 갱신하고, 로그아웃 시 폐기합니다.

`spakky-oidc`와 방향이 반대입니다. `spakky-oidc`는 들어오는 bearer token을 검증하고,
`spakky-oauth`는 나가는 호출에 쓸 token을 얻어 보관합니다.

## 제공 기능

- Authorization code flow 시작: `state`, PKCE `S256` challenge, `openid` scope가 있으면 `nonce` 생성
- Callback code 교환과 token 저장
- 만료 `refresh_leeway_seconds` 전 갱신, refresh token 회전 반영
- 같은 주체의 동시 갱신을 하나로 묶는 process-local 잠금
- 다른 instance가 먼저 회전한 token 재사용
- Revocation endpoint 호출과 local token 삭제

## 포함하지 않는 것

- 로그인·callback HTTP route. Application의 inbound adapter(FastAPI 등)가 `OAuthClient`를 호출합니다.
- ID token 서명·claim 검증. `OAuthAuthorizationResult`가 `tokens.id_token`과 `nonce`를 돌려주므로 application이 검증합니다.
- Confidential client 인증(`client_secret`), device code, client credentials grant.
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
| `client_id` | 필수 | public client id |
| `scopes` | `()` | 요청할 scope |
| `authorization_parameters` | `{}` | authorization 요청에 더할 parameter |
| `token_parameters` | `{}` | code 교환과 refresh 요청에 더할 parameter |

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
`OAuthTokenSet`의 token은 `SecretStr`입니다. 저장할 때 암호화는 저장소 구현의 책임입니다.

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
    result = await oauth.complete_authorization(state, code)
    # result.tokens.id_token과 result.nonce로 ID token을 검증합니다.


async def call_api(oauth: OAuthClient, user_id: str) -> str:
    try:
        return await oauth.access_token("example", user_id)
    except OAuthAuthorizationRequiredError:
        # 다시 로그인이 필요합니다.
        raise
```

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
| `OAuthAuthorizationStateError` | callback `state`를 모르거나 이미 썼거나 만료됨 |
| `OAuthAuthorizationRequiredError` | token이 없거나 grant가 거절되어 다시 로그인해야 함 |
| `OAuthTokenEndpointError` | token endpoint가 grant 거절이 아닌 이유로 실패 |
| `OAuthTokenResponseError` | token 응답이 사용할 수 있는 bearer token이 아님 |
| `OAuthTransportError` | authorization server에 연결하지 못함 |
| `OAuthRevocationError` | local token은 삭제했지만 server가 폐기를 확인하지 않음 |

Refresh grant가 400 또는 401로 거절되면 저장된 token을 삭제하고
`OAuthAuthorizationRequiredError`를 올립니다.

## 라이선스

MIT
