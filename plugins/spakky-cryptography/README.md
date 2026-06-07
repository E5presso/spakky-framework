# spakky-cryptography

`spakky-cryptography` provides retained cryptographic utilities from
`spakky-security` and the auth provider capabilities required by signed
`AuthContextSnapshot` propagation and password hash verification.

## Retained Utilities

- `Key`, `Base64Encoder`, `Hash`, `HMAC`
- `ICryptor`, `ISigner`
- `Aes`, `Gcm`, `Rsa`, `AsymmetricKey`
- `Argon2PasswordEncoder`, `BcryptPasswordEncoder`, `Pbkdf2PasswordEncoder`, `ScryptPasswordEncoder`

JWT/OIDC token validation remains outside this package.

## Auth Provider Capabilities

The plugin registers `CryptographyAuthProvider`, which implements:

- `AuthCapability.SNAPSHOT_SIGN`
- `AuthCapability.SNAPSHOT_VERIFY`
- `AuthCapability.PASSWORD_HASH`
- `AuthCapability.PASSWORD_VERIFY`

Snapshot verification maps missing, invalid, and expired envelopes to
`CHALLENGE` decisions. Provider-unavailable conditions map to `ERROR`.
