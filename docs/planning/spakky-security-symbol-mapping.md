# spakky-security Symbol Mapping

- **Status**: Migration inventory for #297
- **Milestone**: Framework authentication and authorization
- **Removal model**: `spakky-security` is removed without a shim. No
  `spakky.plugins.security` compatibility package, alias module, dependency
  extra, or re-export is introduced during #298.

## Purpose

`spakky-security` bundled three concerns in one utility plugin: standalone
cryptographic primitives, password hashing helpers, and a bespoke HMAC JWT
builder/parser. The authentication milestone splits those concerns before the
package is removed.

- Retained cryptographic primitives move to `spakky-cryptography` with the
  same public class names under the `spakky.plugins.cryptography` namespace.
- Provider-neutral password and snapshot capabilities are exposed through
  `spakky-auth` ports and implemented by `spakky-cryptography`.
- Bearer JWT authentication is owned by `spakky-oidc`; the old bespoke JWT
  utility is intentionally removed instead of being shimmed.

## Import Inventory Coverage

The known `spakky.plugins.security` import surface is covered by this mapping:

| Legacy import | Symbols | Classification | Replacement or removal |
| --- | --- | --- | --- |
| `spakky.plugins.security` | `PLUGIN_NAME` | Intentional removal | Remove the package. No `spakky-security` plugin registration remains. |
| `spakky.plugins.security.main` | `initialize` | Intentional removal | Remove the entry point. `spakky-cryptography` and `spakky-oidc` register their own providers. |
| `spakky.plugins.security.encoding` | `Base64Encoder` | `spakky-cryptography` | `spakky.plugins.cryptography.encoding.Base64Encoder` |
| `spakky.plugins.security.key` | `Key` | `spakky-cryptography` | `spakky.plugins.cryptography.key.Key` |
| `spakky.plugins.security.hash` | `Hash`, `HashType` | `spakky-cryptography` | `spakky.plugins.cryptography.hash.Hash`, `HashType` |
| `spakky.plugins.security.hmac_signer` | `HMAC`, `HMACType` | `spakky-cryptography` | `spakky.plugins.cryptography.hmac_signer.HMAC`, `HMACType` |
| `spakky.plugins.security.cryptography.interface` | `ICryptor`, `ISigner` | `spakky-cryptography` | `spakky.plugins.cryptography.cryptography.interface.ICryptor`, `ISigner` |
| `spakky.plugins.security.cryptography.aes` | `Aes` | `spakky-cryptography` | `spakky.plugins.cryptography.cryptography.aes.Aes` |
| `spakky.plugins.security.cryptography.gcm` | `Gcm` | `spakky-cryptography` | `spakky.plugins.cryptography.cryptography.gcm.Gcm` |
| `spakky.plugins.security.cryptography.rsa` | `AsymmetricKey`, `Rsa` | `spakky-cryptography` | `spakky.plugins.cryptography.cryptography.rsa.AsymmetricKey`, `Rsa` |
| `spakky.plugins.security.password.interface` | `IPasswordEncoder` | `spakky-cryptography` | `spakky.plugins.cryptography.password.interface.IPasswordEncoder` |
| `spakky.plugins.security.password` | `PasswordEncoder` docstring reference | Intentional removal | No concrete `PasswordEncoder` symbol exists in the package. Use a concrete retained encoder or the provider-neutral `spakky.auth.IPasswordHasher` / `IPasswordVerifier` ports. |
| `spakky.plugins.security.password.argon2` | `Argon2PasswordEncoder` | `spakky-cryptography` | `spakky.plugins.cryptography.password.argon2.Argon2PasswordEncoder` |
| `spakky.plugins.security.password.bcrypt` | `BcryptPasswordEncoder` | `spakky-cryptography` | `spakky.plugins.cryptography.password.bcrypt.BcryptPasswordEncoder` |
| `spakky.plugins.security.password.pbkdf2` | `Pbkdf2PasswordEncoder` | `spakky-cryptography` | `spakky.plugins.cryptography.password.pbkdf2.Pbkdf2PasswordEncoder` |
| `spakky.plugins.security.password.scrypt` | `ScryptPasswordEncoder` | `spakky-cryptography` | `spakky.plugins.cryptography.password.scrypt.ScryptPasswordEncoder` |
| `spakky.plugins.security.jwt` | `JWT` | Intentional removal | Do not migrate as a framework utility. Use `spakky-oidc` for OIDC/OAuth bearer JWT authentication. Application-owned token minting should use an application dependency outside Spakky's auth provider surface. |
| `spakky.plugins.security.jwt` | `JWTService` docstring reference | Intentional removal | No concrete `JWTService` symbol exists in the package. Use `spakky-oidc` for provider-owned bearer JWT authentication. |
| `spakky.plugins.security.error` | `DecryptionFailedError`, `KeySizeError`, `PrivateKeyRequiredError`, `CannotImportAsymmetricKeyError`, `InvalidKeyConstructorCallError`, `IncompatibleKeyTypeError`, `PasswordRequiredError`, `AsymmetricKeyRequiredError` | `spakky-cryptography` | Same class names in `spakky.plugins.cryptography.error` |
| `spakky.plugins.security.error` | `InvalidJWTFormatError`, `JWTDecodingError`, `JWTProcessingError` | Intentional removal | Remove together with `JWT`. OIDC bearer validation failures use `spakky.plugins.oidc.error` and provider-neutral auth decisions. |

## Capability Mapping

| Legacy concern | New owner | Notes |
| --- | --- | --- |
| HMAC signing helpers | `spakky-cryptography` | Retained as low-level `HMAC` and `HMACType`; also used internally for `AuthContextSnapshot` envelope signatures. |
| Hash utilities | `spakky-cryptography` | Retained as `Hash` and `HashType` for string and file-stream hashing. |
| Key material wrapper | `spakky-cryptography` | Retained as `Key` with binary, Base64, URL-safe Base64, and hex accessors. |
| Symmetric cryptography | `spakky-cryptography` | `Aes` and `Gcm` are retained under `cryptography.cryptography.*`. |
| Asymmetric cryptography and signatures | `spakky-cryptography` | `AsymmetricKey`, `Rsa`, and `ISigner` are retained under `cryptography.cryptography.*`. |
| Password encoders | `spakky-cryptography` | Low-level encoders are retained. Provider-neutral app integration uses `spakky.auth.IPasswordHasher` and `IPasswordVerifier`, implemented by `CryptographyAuthProvider`. |
| AuthContext snapshot signing and verification | `spakky-cryptography` + `spakky-auth` | `CryptographyAuthProvider` implements `IAuthContextSnapshotSigner` and `IAuthContextSnapshotVerifier`. This is new auth milestone surface, not a `spakky-security` shim. |
| OIDC/OAuth bearer JWT authentication | `spakky-oidc` + `spakky-auth` | `OidcAuthenticationProvider` validates issuer, audience, JWKS signature, token lifetime, and maps claims into `AuthContext`. |
| Bespoke HMAC JWT builder/parser | Intentional removal | The old `JWT` type mixed token minting, HMAC verification, and mutable claim helpers. It is not part of the provider-neutral auth surface and is not reintroduced. |

## Draft Migration Table

| Before | After |
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
| `from spakky.plugins.security.jwt import JWT` | Removed. For inbound bearer JWT authentication, use `spakky.plugins.oidc.OidcAuthenticationProvider` through the `spakky-auth` provider-neutral authentication port. |
| `from spakky.plugins.security.error import InvalidJWTFormatError, JWTDecodingError, JWTProcessingError` | Removed with `JWT`. OIDC validation errors are `AbstractSpakkyOidcError`, `OidcCredentialError`, `OidcDiscoveryError`, `OidcJwksError`, and `OidcTokenValidationError`. |

## Removal Checklist for #298

- Remove `plugins/spakky-security` from the workspace and root dependency table.
- Remove the `security` optional extra that depends on `spakky-security`.
- Remove `spakky-security` from mkdocstrings paths, API nav, package listings,
  README tables, architecture diagrams, glossary examples, and error hierarchy.
- Do not add `spakky.plugins.security` modules that import from
  `spakky.plugins.cryptography` or `spakky.plugins.oidc`.
- Replace retained utility examples with `spakky.plugins.cryptography.*`
  imports.
- Replace bearer JWT authentication examples with `spakky.plugins.oidc` and
  `spakky.auth` provider-neutral types.

## Verification Commands

```bash
rg -n "from spakky\.plugins\.security|import spakky\.plugins\.security" . --glob '*.py' --glob '*.md' --glob '!uv.lock'
uv run mkdocs build --strict
```

The `rg` command should only report locations intentionally handled by this
mapping before #298. After #298, it should report zero retained imports outside
historical changelog text, if any such text is kept.
