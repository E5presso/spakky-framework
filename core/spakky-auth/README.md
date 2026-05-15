# Spakky Auth

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 provider-neutral authentication and authorization core package입니다.

## 설치

```bash
pip install spakky-auth
```

## 현재 범위

`spakky-auth`는 인증/인가 마일스톤의 provider-neutral semantic model을 소유합니다. Provider plugin과 boundary integration이 의존할 수 있는 `spakky.auth` import root, package metadata, workspace registration, documentation API path와 함께 다음 core 계약을 제공합니다.

- `AuthContext`, `AuthSubject`, `AuthClaim`: inbound adapter가 사용자 호출 전에 `ApplicationContext` context value에 seed하는 인증 상태
- `CredentialCarrier`: provider가 해석할 boundary-local credential 전달체
- `AuthorizationDecision`, `AuthorizationDecisionState`, `AuthorizationReasonCode`: `ALLOW`, `CHALLENGE`, `DENY`, `ERROR` 판정 모델
- `AuthContextSnapshot`: raw bearer token 대신 task/broker/saga 등으로 전파하는 signed snapshot envelope 계약
- `AbstractSpakkyAuthError` 기반 auth 오류 hierarchy

ABC port, decorator metadata, AOP enforcement, provider implementation, startup validation은 후속 이슈에서 추가됩니다.

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

현재 `initialize()`는 등록용 no-op입니다. 후속 enforcement component가 추가되면 이 entry point를 통해 feature-local component를 등록합니다.

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
