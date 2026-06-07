# spakky-oidc

`spakky-oidc` authenticates OIDC/OAuth bearer JWT credentials and maps
validated claims into `spakky.auth.AuthContext`.

The provider contributes `AuthCapability.AUTHENTICATION` through the
`spakky.contributions.spakky.auth` entry point. It intentionally contains no
browser login, callback, session, refresh, or logout routes; inbound adapters
pass an already-observed bearer credential to the provider-neutral
`IAuthenticationProvider` port.

## Capabilities

- OIDC discovery from `issuer/.well-known/openid-configuration` or an explicit
  discovery URL.
- JWKS key selection by `kid` and RS256 signature verification.
- `issuer`, `audience`, `azp`, `exp`, `nbf`, `iat`, and clock skew validation.
- `sub`, display name, tenant, role, scope, and selected safe claim mapping to
  `AuthContext`.
- Raw bearer token exclusion from `AuthContext.claims`, `metadata`, and
  `credential_carrier`.

## Installation

```bash
pip install spakky-oidc
```

## Usage

```python
from spakky.auth import (
    AuthInvocation,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
)
from spakky.plugins.oidc import OidcAuthenticationProvider, OidcProviderConfig

provider = OidcAuthenticationProvider(
    config=OidcProviderConfig(
        issuer="https://issuer.example.test",
        audience="api://spakky",
        client_id="spakky-client",
    )
)

auth_context = provider.authenticate(
    CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
        material="eyJ...",
        name="Authorization",
        scheme="Bearer",
    ),
    AuthInvocation(boundary="http", operation="GET /documents"),
)
```

`OidcProviderConfig` controls claim mapping via `roles_claim`, `scopes_claim`,
`tenant_claim`, `display_name_claim`, and `retained_claim_names`. The default
scope claim accepts the standard space-delimited `scope` string; role and custom
scope claims may also use string arrays.

`authenticate_result()` is available for boundary adapters that prefer a
provider-neutral `AuthorizationDecision` instead of exception handling.

## License

MIT License
