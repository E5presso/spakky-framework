"""OAuth 2.0 public client: authorization code with PKCE, refresh, and revocation."""

from asyncio import Lock
from base64 import urlsafe_b64encode
from collections.abc import Mapping
from datetime import datetime, timedelta
from hashlib import sha256
from json import JSONDecodeError
from math import isfinite
from secrets import compare_digest, token_urlsafe
from urllib.parse import urlencode
from weakref import WeakValueDictionary

from httpx import AsyncClient, HTTPError, InvalidURL, Response
from pydantic import SecretStr
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.oauth.config import (
    RESERVED_AUTHORIZATION_PARAMETERS,
    OAuthClientRegistration,
    OAuthConfig,
)
from spakky.plugins.oauth.constants import (
    OAUTH_BEARER_TOKEN_TYPE,
    OAUTH_CODE_CHALLENGE_METHOD,
    OAUTH_CODE_VERIFIER_BYTES,
    OAUTH_NONCE_BYTES,
    OAUTH_OPENID_SCOPE,
    OAUTH_STATE_BYTES,
)
from spakky.plugins.oauth.error import (
    OAuthAuthorizationRequestError,
    OAuthAuthorizationRequiredError,
    OAuthAuthorizationStateError,
    OAuthClientNotConfiguredError,
    OAuthRevocationError,
    OAuthTokenEndpointError,
    OAuthTokenResponseError,
    OAuthTransportError,
)
from spakky.plugins.oauth.store import (
    IOAuthAuthorizationStateStore,
    IOAuthClock,
    IOAuthTokenStore,
    SystemOAuthClock,
)
from spakky.plugins.oauth.token import (
    OAuthAccessToken,
    OAuthAuthorizationCode,
    OAuthAuthorizationRequest,
    OAuthAuthorizationResult,
    OAuthClientId,
    OAuthClientName,
    OAuthPendingAuthorization,
    OAuthRedirectUri,
    OAuthState,
    OAuthSubject,
    OAuthTokenKey,
    OAuthTokenSet,
)

_HTTP_OK = 200
_INVALID_GRANT = "invalid_grant"

# Token endpoint JSON is untrusted input; every field is narrowed before use.
type _TokenPayload = Mapping[str, object]


@Pod()
class OAuthClient:
    """Obtain, refresh, and revoke tokens for application subjects."""

    __config: OAuthConfig
    __tokens: IOAuthTokenStore
    __states: IOAuthAuthorizationStateStore
    __clock: IOAuthClock
    __locks: WeakValueDictionary[OAuthTokenKey, Lock]

    def __init__(
        self,
        config: OAuthConfig,
        token_store: IOAuthTokenStore,
        state_store: IOAuthAuthorizationStateStore,
        clock: IOAuthClock | None = None,
    ) -> None:
        self.__config = config
        self.__tokens = token_store
        self.__states = state_store
        self.__clock = clock if clock is not None else SystemOAuthClock()
        self.__locks = WeakValueDictionary()

    async def begin_authorization(
        self,
        client: OAuthClientName,
        subject: OAuthSubject,
        redirect_uri: OAuthRedirectUri,
        *,
        client_id: OAuthClientId | None = None,
        parameters: Mapping[str, str] | None = None,
    ) -> OAuthAuthorizationRequest:
        """Start an authorization-code flow and return the redirect target.

        Args:
            client: Name of the configured registration.
            subject: Application identity the resulting tokens belong to.
            redirect_uri: Callback URL registered for this flow.
            client_id: Overrides the registered client id, for servers that
                issue a client id per sign-in.
            parameters: Extra authorization parameters for this request only.

        Returns:
            The authorization URL and the state value the callback must echo.

        Raises:
            OAuthAuthorizationRequestError: A request parameter overrides a
                protocol field or the client id override is blank.
        """
        registration = self._registration(client)
        extra = dict(parameters or {})
        if not RESERVED_AUTHORIZATION_PARAMETERS.isdisjoint(extra):
            raise OAuthAuthorizationRequestError
        if client_id is not None and client_id.strip() == "":
            raise OAuthAuthorizationRequestError
        state = token_urlsafe(OAUTH_STATE_BYTES)
        code_verifier = token_urlsafe(OAUTH_CODE_VERIFIER_BYTES)
        nonce = (
            token_urlsafe(OAUTH_NONCE_BYTES)
            if OAUTH_OPENID_SCOPE in registration.scopes
            else None
        )
        effective_client_id = (
            client_id if client_id is not None else registration.client_id
        )
        query: dict[str, str] = {
            **registration.authorization_parameters,
            **extra,
            "response_type": "code",
            "client_id": effective_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": self._code_challenge(code_verifier),
            "code_challenge_method": OAUTH_CODE_CHALLENGE_METHOD,
        }
        if len(registration.scopes) > 0:
            query["scope"] = " ".join(registration.scopes)
        if nonce is not None:
            query["nonce"] = nonce
        await self.__states.save(
            state,
            OAuthPendingAuthorization(
                key=OAuthTokenKey(client=client, subject=subject),
                client_id=effective_client_id,
                redirect_uri=redirect_uri,
                code_verifier=SecretStr(code_verifier),
                nonce=nonce,
                expires_at=self.__clock.now()
                + timedelta(seconds=self.__config.authorization_ttl_seconds),
            ),
        )
        separator = "&" if "?" in registration.authorization_endpoint else "?"
        return OAuthAuthorizationRequest(
            url=f"{registration.authorization_endpoint}{separator}{urlencode(query)}",
            state=state,
        )

    async def complete_authorization(
        self,
        state: OAuthState,
        code: OAuthAuthorizationCode,
        *,
        client_id: OAuthClientId | None = None,
    ) -> OAuthAuthorizationResult:
        """Exchange a callback code for tokens and store them for the subject.

        Args:
            state: State value echoed by the authorization server.
            code: Authorization code from the callback.
            client_id: Client id the server issued in the callback, when it
                differs from the one the flow started with.

        Returns:
            The stored tokens and the nonce an ID token must carry.

        Raises:
            OAuthAuthorizationStateError: The state is unknown, used, or expired.
            OAuthAuthorizationRequestError: The client id override is blank.
            OAuthAuthorizationRequiredError: The server rejected the code.
        """
        if client_id is not None and client_id.strip() == "":
            raise OAuthAuthorizationRequestError
        pending = await self.__states.take(state)
        if pending is None or pending.expires_at <= self.__clock.now():
            raise OAuthAuthorizationStateError
        registration = self._registration(pending.key.client)
        effective_client_id = client_id if client_id is not None else pending.client_id
        response = await self._post(
            registration.token_endpoint,
            {
                **registration.token_parameters,
                "grant_type": "authorization_code",
                "client_id": effective_client_id,
                "code": code,
                "code_verifier": pending.code_verifier.get_secret_value(),
                "redirect_uri": pending.redirect_uri,
            },
        )
        if self._grant_rejected(response):
            raise OAuthAuthorizationRequiredError
        tokens = self._token_set(
            response,
            client_id=effective_client_id,
            default_scopes=registration.scopes,
            previous=None,
        )
        async with self._lock(pending.key):
            await self.__tokens.save(pending.key, tokens)
        return OAuthAuthorizationResult(
            key=pending.key,
            tokens=tokens,
            nonce=pending.nonce,
        )

    async def access_token(
        self,
        client: OAuthClientName,
        subject: OAuthSubject,
        *,
        rejected_token: OAuthAccessToken | None = None,
    ) -> OAuthAccessToken:
        """Return a usable access token, refreshing it when needed.

        Args:
            client: Name of the configured registration.
            subject: Application identity that signed in.
            rejected_token: A token the resource server just rejected; the
                stored token is refreshed only if it is still that token.

        Returns:
            An access token valid beyond the configured refresh leeway.

        Raises:
            OAuthAuthorizationRequiredError: The subject has no tokens, no
                refresh token, or the refresh grant was rejected. Stored
                tokens are kept; call ``revoke`` to clear them.
        """
        registration = self._registration(client)
        key = OAuthTokenKey(client=client, subject=subject)
        async with self._lock(key):
            tokens = await self.__tokens.load(key)
            if tokens is None:
                raise OAuthAuthorizationRequiredError
            rejected = rejected_token is not None and compare_digest(
                tokens.access_token.get_secret_value().encode(),
                rejected_token.encode(),
            )
            if not rejected and self._usable(tokens):
                return tokens.access_token.get_secret_value()
            if tokens.refresh_token is None:
                raise OAuthAuthorizationRequiredError
            response = await self._post(
                registration.token_endpoint,
                {
                    **registration.token_parameters,
                    "grant_type": "refresh_token",
                    "client_id": tokens.client_id,
                    "refresh_token": tokens.refresh_token.get_secret_value(),
                },
            )
            latest = await self.__tokens.load(key)
            if self._grant_rejected(response):
                return self._rotated_elsewhere(tokens, latest)
            refreshed = self._token_set(
                response,
                client_id=tokens.client_id,
                default_scopes=tokens.scopes,
                previous=tokens,
            )
            if latest is None:
                raise OAuthAuthorizationRequiredError
            await self.__tokens.save(key, refreshed)
            return refreshed.access_token.get_secret_value()

    async def revoke(self, client: OAuthClientName, subject: OAuthSubject) -> None:
        """Remove the subject's tokens and revoke them at the server.

        Local tokens are removed first, so the subject is signed out here even
        when the server cannot confirm revocation.

        Raises:
            OAuthRevocationError: The server was unreachable or did not confirm
                revocation.
        """
        registration = self._registration(client)
        key = OAuthTokenKey(client=client, subject=subject)
        async with self._lock(key):
            tokens = await self.__tokens.load(key)
            if tokens is None:
                return
            await self.__tokens.delete(key)
            if registration.revocation_endpoint is None:
                return
            if tokens.refresh_token is not None:
                token = tokens.refresh_token
                hint = "refresh_token"
            else:
                token = tokens.access_token
                hint = "access_token"
            try:
                response = await self._post(
                    registration.revocation_endpoint,
                    {
                        "token": token.get_secret_value(),
                        "token_type_hint": hint,
                        "client_id": tokens.client_id,
                    },
                )
            except OAuthTransportError as error:
                raise OAuthRevocationError from error
            if response.status_code != _HTTP_OK:
                raise OAuthRevocationError

    def _rotated_elsewhere(
        self,
        attempted: OAuthTokenSet,
        latest: OAuthTokenSet | None,
    ) -> OAuthAccessToken:
        """Resolve a rejected refresh grant against what the store holds now.

        Nothing is deleted here: another instance may be about to store the
        tokens its own refresh just won, and removing them would sign the
        subject out.
        """
        if (
            latest is not None
            and latest.access_token != attempted.access_token
            and self._usable(latest)
        ):
            return latest.access_token.get_secret_value()
        raise OAuthAuthorizationRequiredError

    def _grant_rejected(self, response: Response) -> bool:
        """Return whether the server reported the grant itself as invalid."""
        if response.status_code == _HTTP_OK:
            return False
        try:
            payload: object = response.json()  # untrusted JSON narrowed below
        except (JSONDecodeError, UnicodeDecodeError):
            return False
        return isinstance(payload, Mapping) and payload.get("error") == _INVALID_GRANT

    def _registration(self, client: OAuthClientName) -> OAuthClientRegistration:
        registration = self.__config.clients.get(client)
        if registration is None:
            raise OAuthClientNotConfiguredError
        return registration

    def _lock(self, key: OAuthTokenKey) -> Lock:
        """Return the subject's lock; it is dropped once no caller holds it."""
        lock = self.__locks.get(key)
        if lock is None:
            lock = Lock()
            self.__locks[key] = lock
        return lock

    def _usable(self, tokens: OAuthTokenSet) -> bool:
        if tokens.expires_at is None:
            return True
        leeway = timedelta(seconds=self.__config.refresh_leeway_seconds)
        return tokens.expires_at - leeway > self.__clock.now()

    def _code_challenge(self, code_verifier: str) -> str:
        digest = sha256(code_verifier.encode("ascii")).digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    async def _post(self, url: str, form: Mapping[str, str]) -> Response:
        try:
            async with AsyncClient(
                timeout=self.__config.http_timeout_seconds
            ) as http_client:
                return await http_client.post(url, data=dict(form))
        except (HTTPError, InvalidURL) as error:
            raise OAuthTransportError from error

    def _token_set(
        self,
        response: Response,
        *,
        client_id: OAuthClientId,
        default_scopes: tuple[str, ...],
        previous: OAuthTokenSet | None,
    ) -> OAuthTokenSet:
        if response.status_code != _HTTP_OK:
            raise OAuthTokenEndpointError
        try:
            payload: object = response.json()  # untrusted JSON narrowed below
        except (JSONDecodeError, UnicodeDecodeError) as error:
            raise OAuthTokenResponseError from error
        if not isinstance(payload, Mapping):
            raise OAuthTokenResponseError
        access_token = payload.get("access_token")
        token_type = payload.get("token_type", OAUTH_BEARER_TOKEN_TYPE)
        if (
            not isinstance(access_token, str)
            or access_token.strip() == ""
            or not isinstance(token_type, str)
            or token_type.casefold() != OAUTH_BEARER_TOKEN_TYPE
        ):
            raise OAuthTokenResponseError
        return OAuthTokenSet(
            client_id=client_id,
            access_token=SecretStr(access_token),
            refresh_token=self._rotated_secret(
                payload,
                "refresh_token",
                previous.refresh_token if previous is not None else None,
            ),
            id_token=self._rotated_secret(
                payload,
                "id_token",
                previous.id_token if previous is not None else None,
            ),
            expires_at=self._expires_at(payload),
            scopes=self._scopes(payload, default_scopes),
        )

    def _rotated_secret(
        self,
        payload: _TokenPayload,
        name: str,
        previous: SecretStr | None,
    ) -> SecretStr | None:
        value = payload.get(name)
        if value is None:
            return previous
        if not isinstance(value, str) or value.strip() == "":
            raise OAuthTokenResponseError
        return SecretStr(value)

    def _expires_at(self, payload: _TokenPayload) -> datetime | None:
        expires_in = payload.get("expires_in")
        if expires_in is None:
            return None
        if isinstance(expires_in, str):
            try:
                expires_in = float(expires_in)
            except ValueError as error:
                raise OAuthTokenResponseError from error
        if isinstance(expires_in, bool) or not isinstance(expires_in, int | float):
            raise OAuthTokenResponseError
        try:
            if not isfinite(expires_in) or expires_in <= 0:
                raise OAuthTokenResponseError
            return self.__clock.now() + timedelta(seconds=expires_in)
        except OverflowError as error:
            # Integers beyond float range and lifetimes beyond datetime range.
            raise OAuthTokenResponseError from error

    def _scopes(
        self,
        payload: _TokenPayload,
        default_scopes: tuple[str, ...],
    ) -> tuple[str, ...]:
        scope = payload.get("scope")
        if scope is None:
            return default_scopes
        if not isinstance(scope, str):
            raise OAuthTokenResponseError
        return tuple(scope.split())
