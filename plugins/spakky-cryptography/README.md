# spakky-cryptography

> `spakky-cryptography`는 암호화 utility와 서명된 `AuthContextSnapshot` 전파를 제공합니다.
> Password hash 검증과 snapshot sign/verify capability를 `spakky-auth` provider contribution으로 연결합니다.

## 유지되는 Utility

- `Key`, `Base64Encoder`, `Hash`, `HMAC`
- `ICryptor`, `ISigner`
- `Aes`, `Gcm`, `Rsa`, `AsymmetricKey`
- `Argon2PasswordEncoder`, `BcryptPasswordEncoder`, `Pbkdf2PasswordEncoder`, `ScryptPasswordEncoder`

JWT/OIDC token 검증은 이 패키지의 범위 밖이며 `spakky-oidc`가 담당합니다.

## 설치

```bash
pip install spakky-cryptography
```

Auth snapshot propagation이나 password provider로 쓰려면 `spakky-auth`와 함께 로드합니다.

```bash
pip install spakky-auth spakky-cryptography
```

## 설정

`CryptographyAuthProviderConfig`는 `SPAKKY_CRYPTOGRAPHY_` 접두사의 환경변수를 읽습니다.

| 환경변수 | 의미 | 기본값 |
| --- | --- | --- |
| `SPAKKY_CRYPTOGRAPHY_SNAPSHOT_KEY` | snapshot HMAC key, URL-safe base64 문자열 | 런타임 생성 32-byte key |
| `SPAKKY_CRYPTOGRAPHY_SNAPSHOT_KEY_ID` | signed snapshot envelope에 들어갈 key id | `spakky-cryptography:default` |
| `SPAKKY_CRYPTOGRAPHY_SNAPSHOT_TTL` | 새 snapshot 유효 기간 | `5m` |
| `SPAKKY_CRYPTOGRAPHY_VERIFICATION_AVAILABLE` | snapshot verification provider 가용성 | `true` |
| `SPAKKY_CRYPTOGRAPHY_PASSWORD_AVAILABLE` | password hash/verify provider 가용성 | `true` |

운영에서는 모든 프로세스가 같은 snapshot을 검증할 수 있도록 `SNAPSHOT_KEY`를 명시적으로 고정하세요. 기본 key는 프로세스 시작마다 생성되므로 단일 프로세스 개발용입니다.

## Auth Provider Capability

플러그인은 다음 capability를 구현하는 `CryptographyAuthProvider`를 등록합니다.

- `AuthCapability.SNAPSHOT_SIGN`
- `AuthCapability.SNAPSHOT_VERIFY`
- `AuthCapability.PASSWORD_HASH`
- `AuthCapability.PASSWORD_VERIFY`

Snapshot verification은 누락, invalid, expired envelope을 `CHALLENGE` decision으로
매핑합니다. Provider를 사용할 수 없는 상태는 `ERROR`로 매핑합니다.

## 플러그인 등록

Base plugin entry point는 `CryptographyAuthProviderConfig`, `CryptographyAuthProvider`를 등록하고 다음 port를 같은 provider 구현체에 binding합니다.

- `IAuthContextSnapshotSigner`
- `IAuthContextSnapshotVerifier`
- `IPasswordHasher`
- `IPasswordVerifier`

Auth feature contribution entry point는 `spakky.contributions.spakky.auth` group에 `AuthProviderContribution` capability metadata를 등록합니다. `spakky-auth`의 startup validation은 이 metadata로 snapshot/password capability provider count를 검증합니다.

## 사용 예

```python
import spakky.auth
import spakky.plugins.cryptography
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.cryptography.PLUGIN_NAME,
        }
    )
    .start()
)
```

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
