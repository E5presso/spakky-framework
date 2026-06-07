# 인증/인가 전환 가이드

> 제거된 `spakky-security` import를 현재 `spakky-auth` provider 구조와 retained cryptography API로 옮기는 기준입니다.

기존 `spakky-security` 패키지는 호환 shim 없이 제거되었습니다. Compatibility module, alias package, optional extra, re-export를 새로 만들지 마세요. 유지되는 암호화 utility는 `spakky-cryptography`로 옮기고, inbound bearer JWT 인증은 `spakky-oidc`로 처리하며, 프레임워크 차원의 auth decision은 `spakky-auth` port를 통해 다룹니다.

이 문서는 제거된 import 경로를 기록할 수 있는 유일한 allowlist 위치이기도 합니다. 새 코드와 다른 문서에서는 제거된 패키지명이나 예전 import root를 언급하지 마세요.

---

## 패키지와 플러그인 변경

의존성과 plugin include 목록에서 예전 패키지를 제거합니다. 그 다음 런타임에 필요한 패키지만 추가하세요.

```bash
pip install spakky-auth spakky-cryptography spakky-oidc spakky-policy spakky-openfga
```

| 관심사 | 새 담당 패키지 |
| --- | --- |
| Hash, HMAC, key, encoding, AES, GCM, RSA | `spakky-cryptography` |
| Password encoder class | `spakky-cryptography` |
| Password hash/verify port | `spakky-auth` port, `spakky-cryptography` 구현 |
| `AuthContextSnapshot` sign/verify | `spakky-auth` snapshot 계약, `spakky-cryptography` 구현 |
| Inbound bearer JWT authentication | `spakky-oidc`가 `IAuthenticationProvider`로 제공 |
| Role, scope, permission, policy decision | `spakky-policy` 또는 같은 port를 구현하는 provider |
| Relationship check | `spakky-openfga`가 `IRelationChecker`로 제공 |

---

## 예전 import 매핑

| 예전 import | 대체 import |
| --- | --- |
| `from spakky.plugins.security.key import Key` | `from spakky.plugins.cryptography.key import Key` |
| `from spakky.plugins.security.encoding import Base64Encoder` | `from spakky.plugins.cryptography.encoding import Base64Encoder` |
| `from spakky.plugins.security.hash import Hash, HashType` | `from spakky.plugins.cryptography.hash import Hash, HashType` |
| `from spakky.plugins.security.hmac_signer import HMAC, HMACType` | `from spakky.plugins.cryptography.hmac_signer import HMAC, HMACType` |
| `from spakky.plugins.security.cryptography.interface import ICryptor, ISigner` | `from spakky.plugins.cryptography.cryptography.interface import ICryptor, ISigner` |
| `from spakky.plugins.security.cryptography.aes import Aes` | `from spakky.plugins.cryptography.cryptography.aes import Aes` |
| `from spakky.plugins.security.cryptography.gcm import Gcm` | `from spakky.plugins.cryptography.cryptography.gcm import Gcm` |
| `from spakky.plugins.security.cryptography.rsa import AsymmetricKey, Rsa` | `from spakky.plugins.cryptography.cryptography.rsa import AsymmetricKey, Rsa` |
| `from spakky.plugins.security.password.interface import IPasswordEncoder` | `from spakky.plugins.cryptography.password.interface import IPasswordEncoder` |
| `from spakky.plugins.security.password.argon2 import Argon2PasswordEncoder` | `from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder` |
| `from spakky.plugins.security.password.bcrypt import BcryptPasswordEncoder` | `from spakky.plugins.cryptography.password.bcrypt import BcryptPasswordEncoder` |
| `from spakky.plugins.security.password.pbkdf2 import Pbkdf2PasswordEncoder` | `from spakky.plugins.cryptography.password.pbkdf2 import Pbkdf2PasswordEncoder` |
| `from spakky.plugins.security.password.scrypt import ScryptPasswordEncoder` | `from spakky.plugins.cryptography.password.scrypt import ScryptPasswordEncoder` |
| `from spakky.plugins.security.error import DecryptionFailedError, KeySizeError, PrivateKeyRequiredError, CannotImportAsymmetricKeyError, InvalidKeyConstructorCallError, IncompatibleKeyTypeError, PasswordRequiredError, AsymmetricKeyRequiredError` | `from spakky.plugins.cryptography.error import DecryptionFailedError, KeySizeError, PrivateKeyRequiredError, CannotImportAsymmetricKeyError, InvalidKeyConstructorCallError, IncompatibleKeyTypeError, PasswordRequiredError, AsymmetricKeyRequiredError` |

기존 JWT utility는 의도적으로 제거되었습니다.

| 예전 import | 처리 방법 |
| --- | --- |
| `from spakky.plugins.security.jwt import JWT` | 제거됨. Inbound bearer JWT 인증은 `spakky-oidc`를 설정하고 adapter가 `IAuthenticationProvider`를 호출하게 합니다. 애플리케이션이 직접 token을 발급하는 기능은 Spakky provider surface가 아닙니다. |
| `from spakky.plugins.security.error import InvalidJWTFormatError, JWTDecodingError, JWTProcessingError` | 기존 JWT utility와 함께 제거됨. OIDC 검증 실패는 `AbstractSpakkyOidcError`, `OidcCredentialError`, `OidcDiscoveryError`, `OidcJwksError`, `OidcTokenValidationError`로 다룹니다. |

---

## 전환 순서

1. 유지되는 crypto utility import를 `spakky.plugins.cryptography.*`로 바꿉니다.
2. 프레임워크 레벨의 bearer JWT parsing을 제거하고, `spakky-auth`를 통해 로드되는 OIDC provider로 대체합니다.
3. Route, command, task, event handler, saga 보호는 `spakky.auth`의 `@protected`와 requirement decorator로 옮깁니다.
4. 분산 작업에서는 signed snapshot propagation을 켜고, snapshot signer/verifier provider를 각각 정확히 하나 등록합니다.
5. Custom token 발급, browser login/session lifecycle, audit logging, data filtering, authorization model administration은 애플리케이션 코드나 별도 서비스에 둡니다. 이 기능들은 현재 구현된 provider surface가 아닙니다.

```python
from spakky.auth import protected, require_scope


@require_scope("documents:read")
@protected
def read_document() -> str:
    return "ok"
```

---

## R03 최종 grep allowlist

R03는 제거된 패키지에 대한 역사적 언급이 이 전환 가이드에만 남아 있음을 증명해야 합니다. R04가 merge된 뒤 repository root에서 다음 명령을 실행합니다.

```bash
rg -n "spakky-security|spakky\.plugins\.security" . --glob '*.py' --glob '*.md' --glob '!uv.lock'
```

예상 match는 이 파일로 제한됩니다. `docs/guides/security.md`는 이 문서로 연결하지만, 제거된 패키지명과 예전 import root를 직접 적지 않습니다.

허용 정책:

| Pattern | 허용 경로 | 사유 |
| --- | --- | --- |
| `spakky-security` | `docs/guides/auth-migration.md` | 제거된 패키지명을 전환 설명에 보존하기 위함 |
| `spakky.plugins.security` | `docs/guides/auth-migration.md` | 예전 import root를 매핑 표에 보존하기 위함 |

Source code, package README, API reference, planning docs, root docs, pyproject, examples에서 match가 나오면 실패입니다. 제거된 패키지는 계속 없어야 하며, 이 문서는 compatibility contract가 아닙니다.
