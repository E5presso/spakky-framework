# 인증/인가 전환 가이드

The legacy `spakky-security` package was removed without a shim. Do not add compatibility modules, alias packages, optional extras, or re-exports. Migrate retained cryptographic utilities to `spakky-cryptography`, use `spakky-oidc` for inbound bearer JWT authentication, and use `spakky-auth` provider-neutral ports for framework auth decisions.

This guide is also the allowlisted location for historical old imports. New code and docs outside this page should not mention the removed package or its old import root.

---

## Package and plugin changes

Remove the old package from dependencies and plugin includes. Add only the packages that match your runtime needs.

```bash
pip install spakky-auth spakky-cryptography spakky-oidc spakky-policy spakky-openfga
```

| Concern | New owner |
| --- | --- |
| Hash, HMAC, key, encoding, AES, GCM, RSA | `spakky-cryptography` |
| Password encoder classes | `spakky-cryptography` |
| Provider-neutral password hash/verify ports | `spakky-auth` ports, implemented by `spakky-cryptography` |
| AuthContextSnapshot sign/verify | `spakky-auth` snapshot contract, implemented by `spakky-cryptography` |
| Inbound bearer JWT authentication | `spakky-oidc` through `IAuthenticationProvider` |
| Role, scope, permission, policy decisions | `spakky-policy` or another provider implementing the same ports |
| Relationship checks | `spakky-openfga` through `IRelationChecker` |

---

## Historical import mapping

| Old import | Replacement |
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

The old JWT utility is intentionally removed:

| Old import | Action |
| --- | --- |
| `from spakky.plugins.security.jwt import JWT` | Removed. For inbound bearer JWT authentication, configure `spakky-oidc` and let adapters call `IAuthenticationProvider`. Application-owned token minting is outside Spakky's provider surface. |
| `from spakky.plugins.security.error import InvalidJWTFormatError, JWTDecodingError, JWTProcessingError` | Removed with the old JWT utility. OIDC validation failures are `AbstractSpakkyOidcError`, `OidcCredentialError`, `OidcDiscoveryError`, `OidcJwksError`, and `OidcTokenValidationError`. |

---

## Auth migration steps

1. Replace retained crypto utility imports with `spakky.plugins.cryptography.*` imports.
2. Replace framework-level bearer JWT parsing with an OIDC provider loaded through `spakky-auth`.
3. Move route, command, task, event handler, and saga protection to `@protected` and the requirement decorators from `spakky.auth`.
4. For distributed work, enable signed snapshot propagation and register exactly one snapshot signer/verifier provider.
5. Keep custom token minting, browser login/session lifecycle, audit logging, data filtering, and authorization model administration in application code or dedicated services. They are not part of the implemented provider surface.

```python
from spakky.auth import protected, require_scope


@require_scope("documents:read")
@protected
def read_document() -> str:
    return "ok"
```

---

## R03 final grep allowlist

R03 should prove that historical references to the removed package exist only in this migration guide. Use these commands from the repository root after R04 is merged:

```bash
rg -n "spakky-security|spakky\.plugins\.security" . --glob '*.py' --glob '*.md' --glob '!uv.lock'
```

Allowed match policy:

| Pattern | Allowed path | Reason |
| --- | --- | --- |
| `spakky-security` | `docs/guides/auth-migration.md` | Historical removed package name in migration prose only. |
| `spakky.plugins.security` | `docs/guides/auth-migration.md` | Historical old import root in migration mapping only. |

Any match in source code, package README files, API reference pages, planning docs, root docs, pyproject files, or examples is a failure. The removed package must stay absent; this guide is not a compatibility contract.
