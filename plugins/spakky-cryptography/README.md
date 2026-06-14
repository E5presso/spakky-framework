# spakky-cryptography

> `spakky-cryptography`는 암호화 utility와 서명된 `AuthContextSnapshot` 전파를 제공합니다.
> Password hash 검증과 snapshot sign/verify capability를 `spakky-auth` provider contribution으로 연결합니다.

## 유지되는 Utility

- `Key`, `Base64Encoder`, `Hash`, `HMAC`
- `ICryptor`, `ISigner`
- `Aes`, `Gcm`, `Rsa`, `AsymmetricKey`
- `Argon2PasswordEncoder`, `BcryptPasswordEncoder`, `Pbkdf2PasswordEncoder`, `ScryptPasswordEncoder`

JWT/OIDC token 검증은 이 패키지의 범위 밖이며 `spakky-oidc`가 담당합니다.

## Auth Provider Capability

플러그인은 다음 capability를 구현하는 `CryptographyAuthProvider`를 등록합니다.

- `AuthCapability.SNAPSHOT_SIGN`
- `AuthCapability.SNAPSHOT_VERIFY`
- `AuthCapability.PASSWORD_HASH`
- `AuthCapability.PASSWORD_VERIFY`

Snapshot verification은 누락, invalid, expired envelope을 `CHALLENGE` decision으로
매핑합니다. Provider를 사용할 수 없는 상태는 `ERROR`로 매핑합니다.
