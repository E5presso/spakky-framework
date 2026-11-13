"""Value types exchanged with the OAuth 2.0 client and its stores."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, SecretStr

type OAuthClientName = str
type OAuthSubject = str
type OAuthState = str
type OAuthAuthorizationCode = str
type OAuthRedirectUri = str
type OAuthClientId = str
type OAuthAccessToken = str


@dataclass(frozen=True, slots=True)
class OAuthTokenKey:
    """Identify the tokens one application subject holds for one registration."""

    client: OAuthClientName
    subject: OAuthSubject


class OAuthTokenSet(BaseModel):
    """Tokens issued to one subject; secrets stay wrapped until they are sent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: OAuthClientId
    access_token: SecretStr
    # None when the server issued no refresh token; expiry then requires sign-in.
    refresh_token: SecretStr | None = None
    # None when the grant did not include the openid scope.
    id_token: SecretStr | None = None
    # None when the server reported no lifetime; valid until a caller rejects it.
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()


class OAuthPendingAuthorization(BaseModel):
    """PKCE and binding data kept between the authorization redirect and callback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: OAuthTokenKey
    client_id: OAuthClientId
    redirect_uri: OAuthRedirectUri
    code_verifier: SecretStr
    # None when the request did not ask for an ID token.
    nonce: str | None = None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class OAuthAuthorizationRequest:
    """Redirect target that starts one authorization-code flow."""

    url: str
    state: OAuthState


@dataclass(frozen=True, slots=True)
class OAuthAuthorizationResult:
    """Tokens stored by a completed flow plus the nonce to check an ID token."""

    key: OAuthTokenKey
    tokens: OAuthTokenSet
    # None when the request did not ask for an ID token.
    nonce: str | None
