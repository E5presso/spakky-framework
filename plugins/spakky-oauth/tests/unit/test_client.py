"""Tests for the OAuth 2.0 client flows over a fake authorization server."""

from asyncio import gather, sleep
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import override
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from pytest import MonkeyPatch

from spakky.plugins.oauth import client as client_module
from spakky.plugins.oauth.client import OAuthClient
from spakky.plugins.oauth.config import OAuthClientRegistration, OAuthConfig
from spakky.plugins.oauth.error import (
    AbstractSpakkyOAuthError,
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
    IOAuthClock,
    InMemoryOAuthAuthorizationStateStore,
    InMemoryOAuthTokenStore,
)
from spakky.plugins.oauth.token import OAuthTokenKey, OAuthTokenSet

type _Reply = httpx.Response | BaseException

_NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
_KEY = OAuthTokenKey(client="example", subject="user-1")
_REDIRECT = "https://app.example.test/auth/callback"


class _Clock(IOAuthClock):
    def __init__(self) -> None:
        self.current = _NOW

    @override
    def now(self) -> datetime:
        return self.current


class _Server:
    """Scripted authorization server recorded behind httpx."""

    def __init__(self) -> None:
        self.replies: list[_Reply] = []
        self.requests: list[httpx.Request] = []
        self.timeouts: list[float] = []

    def client(self, *, timeout: float) -> httpx.AsyncClient:
        self.timeouts.append(timeout)
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # Yield once so concurrent callers really overlap on the subject lock.
        await sleep(0)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def form(self, index: int = 0) -> dict[str, str]:
        parsed = parse_qs(self.requests[index].content.decode())
        return {name: values[0] for name, values in parsed.items()}


class _SwappingTokenStore(InMemoryOAuthTokenStore):
    """Replace the stored tokens after the first load, like another instance would."""

    def __init__(self, replacement: OAuthTokenSet | None) -> None:
        super().__init__()
        self._replacement = replacement
        self._loads = 0

    @override
    async def load(self, key: OAuthTokenKey) -> OAuthTokenSet | None:
        loaded = await super().load(key)
        self._loads += 1
        if self._loads == 1:
            if self._replacement is None:
                await super().delete(key)
            else:
                await super().save(key, self._replacement)
        return loaded


@pytest.fixture
def server(monkeypatch: MonkeyPatch) -> _Server:
    server = _Server()
    monkeypatch.setattr(client_module, "AsyncClient", server.client)
    return server


def _registration(
    *,
    scopes: tuple[str, ...] = ("openid", "offline_access"),
    revocation_endpoint: str | None = "https://auth.example.test/revoke",
    authorization_endpoint: str = "https://auth.example.test/authorize",
) -> OAuthClientRegistration:
    return OAuthClientRegistration(
        authorization_endpoint=authorization_endpoint,
        token_endpoint="https://auth.example.test/token",
        revocation_endpoint=revocation_endpoint,
        client_id="my-app",
        scopes=scopes,
        authorization_parameters={"audience": "api"},
        token_parameters={"resource": "https://api.example.test"},
    )


class _Harness:
    def __init__(
        self,
        registration: OAuthClientRegistration | None = None,
        token_store: InMemoryOAuthTokenStore | None = None,
    ) -> None:
        self.clock = _Clock()
        self.tokens = (
            token_store if token_store is not None else InMemoryOAuthTokenStore()
        )
        self.states = InMemoryOAuthAuthorizationStateStore()
        config = OAuthConfig().model_copy(
            update={"clients": {"example": registration or _registration()}}
        )
        self.client = OAuthClient(config, self.tokens, self.states, self.clock)

    async def hold(
        self,
        *,
        access_token: str = "access-1",
        refresh_token: str | None = "refresh-1",
        expires_in: float | None = 3600,
    ) -> OAuthTokenSet:
        tokens = _tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
        await self.tokens.save(_KEY, tokens)
        return tokens


def _tokens(
    *,
    access_token: str = "access-1",
    refresh_token: str | None = "refresh-1",
    expires_in: float | None = 3600,
) -> OAuthTokenSet:
    return OAuthTokenSet(
        client_id="my-app",
        access_token=SecretStr(access_token),
        refresh_token=SecretStr(refresh_token) if refresh_token is not None else None,
        expires_at=_NOW + timedelta(seconds=expires_in)
        if expires_in is not None
        else None,
        scopes=("openid", "offline_access"),
    )


def _token_reply(**overrides: object) -> httpx.Response:
    payload: dict[str, object] = {
        "access_token": "access-2",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "refresh-2",
    }
    payload.update(overrides)
    return httpx.Response(
        200,
        json={name: value for name, value in payload.items() if value is not None},
    )


def _query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


async def test_begin_authorization_expect_pkce_redirect_and_pending_state() -> None:
    """Starting a flow yields an S256 PKCE redirect bound to a stored verifier."""
    harness = _Harness()

    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)

    query = _query(request.url)
    pending = await harness.states.take(request.state)
    assert pending is not None
    challenge = urlsafe_b64encode(
        sha256(pending.code_verifier.get_secret_value().encode()).digest()
    )
    assert request.url.startswith("https://auth.example.test/authorize?")
    assert query["response_type"] == "code"
    assert query["client_id"] == "my-app"
    assert query["redirect_uri"] == _REDIRECT
    assert query["scope"] == "openid offline_access"
    assert query["state"] == request.state
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] == challenge.decode().rstrip("=")
    assert query["audience"] == "api"
    assert query["nonce"] == pending.nonce
    assert pending.key == _KEY
    assert pending.redirect_uri == _REDIRECT
    assert pending.expires_at == _NOW + timedelta(seconds=600)
    assert len(pending.code_verifier.get_secret_value()) >= 43


async def test_begin_authorization_without_scopes_expect_no_scope_or_nonce() -> None:
    """A registration without scopes sends neither scope nor an OIDC nonce."""
    harness = _Harness(
        _registration(
            scopes=(),
            authorization_endpoint="https://auth.example.test/authorize?tenant=a",
        )
    )

    request = await harness.client.begin_authorization(
        "example",
        "user-1",
        _REDIRECT,
        client_id="issued-client",
        parameters={"login_hint": "user@example.test"},
    )

    query = _query(request.url)
    pending = await harness.states.take(request.state)
    assert pending is not None
    assert "scope" not in query
    assert "nonce" not in query
    assert query["tenant"] == "a"
    assert query["client_id"] == "issued-client"
    assert query["login_hint"] == "user@example.test"
    assert pending.client_id == "issued-client"
    assert pending.nonce is None


async def test_begin_authorization_for_unknown_client_expect_not_configured() -> None:
    """An unknown registration name fails before any state is stored."""
    with pytest.raises(OAuthClientNotConfiguredError):
        await _Harness().client.begin_authorization("missing", "user-1", _REDIRECT)


async def test_complete_authorization_expect_code_exchanged_and_tokens_stored(
    server: _Server,
) -> None:
    """The callback code is exchanged with the PKCE verifier and tokens are kept."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)
    nonce = _query(request.url)["nonce"]
    server.replies = [_token_reply(id_token="id-token", scope="openid offline_access")]

    result = await harness.client.complete_authorization(request.state, "code-1")

    form = server.form()
    stored = await harness.tokens.load(_KEY)
    assert str(server.requests[0].url) == "https://auth.example.test/token"
    assert form["grant_type"] == "authorization_code"
    assert form["client_id"] == "my-app"
    assert form["code"] == "code-1"
    assert form["redirect_uri"] == _REDIRECT
    assert form["resource"] == "https://api.example.test"
    assert len(form["code_verifier"]) >= 43
    assert server.timeouts == [20.0]
    assert result.key == _KEY
    assert result.nonce == nonce
    assert result.tokens == stored
    assert result.tokens.access_token.get_secret_value() == "access-2"
    assert result.tokens.refresh_token == SecretStr("refresh-2")
    assert result.tokens.id_token == SecretStr("id-token")
    assert result.tokens.expires_at == _NOW + timedelta(seconds=3600)
    assert result.tokens.scopes == ("openid", "offline_access")
    assert "access-2" not in repr(result)


async def test_complete_authorization_with_issued_client_id_expect_it_stored(
    server: _Server,
) -> None:
    """A client id issued in the callback is used for the exchange and kept."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)
    server.replies = [
        _token_reply(token_type=None, expires_in=None, refresh_token=None)
    ]

    result = await harness.client.complete_authorization(
        request.state,
        "code-1",
        client_id="issued-client",
    )

    assert server.form()["client_id"] == "issued-client"
    assert result.tokens.client_id == "issued-client"
    assert result.tokens.refresh_token is None
    assert result.tokens.id_token is None
    assert result.tokens.expires_at is None
    assert result.tokens.scopes == ("openid", "offline_access")


async def test_complete_authorization_twice_expect_state_error(server: _Server) -> None:
    """A state value can complete only one flow."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)
    server.replies = [_token_reply()]
    await harness.client.complete_authorization(request.state, "code-1")

    with pytest.raises(OAuthAuthorizationStateError):
        await harness.client.complete_authorization(request.state, "code-1")

    assert len(server.requests) == 1


async def test_complete_authorization_after_ttl_expect_state_error(
    server: _Server,
) -> None:
    """A callback arriving after the authorization TTL is refused."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)
    harness.clock.current = _NOW + timedelta(seconds=600)

    with pytest.raises(OAuthAuthorizationStateError):
        await harness.client.complete_authorization(request.state, "code-1")

    assert server.requests == []


async def test_complete_authorization_with_unknown_state_expect_state_error(
    server: _Server,
) -> None:
    """A forged state never reaches the token endpoint."""
    with pytest.raises(OAuthAuthorizationStateError):
        await _Harness().client.complete_authorization("forged", "code-1")

    assert server.requests == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            httpx.Response(400, json={"error": "invalid_grant"}),
            OAuthAuthorizationRequiredError,
        ),
        (
            httpx.Response(401, json={"error": "invalid_client"}),
            OAuthTokenEndpointError,
        ),
        (httpx.Response(400, content=b"gateway error"), OAuthTokenEndpointError),
        (httpx.Response(400, json=["invalid_grant"]), OAuthTokenEndpointError),
        (httpx.Response(503), OAuthTokenEndpointError),
        (httpx.Response(200, content=b"not-json"), OAuthTokenResponseError),
        (httpx.Response(200, content=b"\xff\xfe"), OAuthTokenResponseError),
        (httpx.Response(200, json=["not", "an", "object"]), OAuthTokenResponseError),
        (_token_reply(access_token=None), OAuthTokenResponseError),
        (_token_reply(access_token=" "), OAuthTokenResponseError),
        (_token_reply(token_type="mac"), OAuthTokenResponseError),
        (_token_reply(token_type=7), OAuthTokenResponseError),
        (_token_reply(expires_in=True), OAuthTokenResponseError),
        (_token_reply(expires_in="soon"), OAuthTokenResponseError),
        (_token_reply(expires_in=-5), OAuthTokenResponseError),
        (_token_reply(expires_in=1e300), OAuthTokenResponseError),
        (_token_reply(expires_in=10**400), OAuthTokenResponseError),
        (
            httpx.Response(
                200,
                content=b'{"access_token":"a","expires_in":Infinity}',
            ),
            OAuthTokenResponseError,
        ),
        (_token_reply(refresh_token=" "), OAuthTokenResponseError),
        (_token_reply(id_token=7), OAuthTokenResponseError),
        (_token_reply(scope=["openid"]), OAuthTokenResponseError),
        (httpx.ConnectError("refused"), OAuthTransportError),
        (httpx.ReadTimeout("slow"), OAuthTransportError),
    ],
)
async def test_complete_authorization_with_bad_reply_expect_typed_error(
    server: _Server,
    reply: _Reply,
    expected: type[AbstractSpakkyOAuthError],
) -> None:
    """Rejected codes, server failures, and unusable token bodies store nothing."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)
    server.replies = [reply]

    with pytest.raises(expected):
        await harness.client.complete_authorization(request.state, "code-1")

    assert await harness.tokens.load(_KEY) is None


async def test_access_token_while_fresh_expect_no_refresh(server: _Server) -> None:
    """A token valid beyond the leeway is returned without contacting the server."""
    harness = _Harness()
    await harness.hold(expires_in=91)

    token = await harness.client.access_token("example", "user-1")

    assert token == "access-1"
    assert server.requests == []


async def test_access_token_without_expiry_expect_usable_until_rejected(
    server: _Server,
) -> None:
    """A token with no reported lifetime is used until a caller rejects it."""
    harness = _Harness()
    await harness.hold(expires_in=None)

    token = await harness.client.access_token("example", "user-1")

    assert token == "access-1"
    assert server.requests == []


async def test_access_token_inside_leeway_expect_refresh_and_rotation(
    server: _Server,
) -> None:
    """A token about to expire is refreshed and the rotated tokens are stored."""
    harness = _Harness()
    await harness.hold(expires_in=90)
    server.replies = [_token_reply()]

    token = await harness.client.access_token("example", "user-1")

    form = server.form()
    stored = await harness.tokens.load(_KEY)
    assert token == "access-2"
    assert form == {
        "grant_type": "refresh_token",
        "client_id": "my-app",
        "refresh_token": "refresh-1",
        "resource": "https://api.example.test",
    }
    assert stored is not None
    assert stored.refresh_token == SecretStr("refresh-2")
    assert stored.expires_at == _NOW + timedelta(seconds=3600)
    assert stored.scopes == ("openid", "offline_access")


async def test_access_token_refresh_without_new_refresh_token_expect_old_kept(
    server: _Server,
) -> None:
    """A server that does not rotate refresh tokens keeps the existing one."""
    harness = _Harness()
    await harness.hold(expires_in=0)
    server.replies = [_token_reply(refresh_token=None, scope="openid")]

    await harness.client.access_token("example", "user-1")

    stored = await harness.tokens.load(_KEY)
    assert stored is not None
    assert stored.refresh_token == SecretStr("refresh-1")
    assert stored.scopes == ("openid",)


async def test_access_token_with_rejected_current_token_expect_refresh(
    server: _Server,
) -> None:
    """A still-unexpired token the resource server rejected is refreshed."""
    harness = _Harness()
    await harness.hold()
    server.replies = [_token_reply()]

    token = await harness.client.access_token(
        "example",
        "user-1",
        rejected_token="access-1",
    )

    assert token == "access-2"
    assert len(server.requests) == 1


async def test_access_token_with_stale_rejected_token_expect_current_token(
    server: _Server,
) -> None:
    """A rejected old token cannot force rotation of a newer stored token."""
    harness = _Harness()
    await harness.hold(access_token="access-9")

    token = await harness.client.access_token(
        "example",
        "user-1",
        rejected_token="access-1",
    )

    assert token == "access-9"
    assert server.requests == []


async def test_concurrent_access_token_calls_expect_single_refresh(
    server: _Server,
) -> None:
    """Concurrent callers for one subject share one refresh."""
    harness = _Harness()
    await harness.hold(expires_in=0)
    server.replies = [_token_reply()]

    tokens = await gather(
        harness.client.access_token("example", "user-1"),
        harness.client.access_token("example", "user-1"),
    )

    assert tokens == ["access-2", "access-2"]
    assert len(server.requests) == 1


async def test_access_token_without_sign_in_expect_authorization_required(
    server: _Server,
) -> None:
    """A subject that never signed in must authorize first."""
    with pytest.raises(OAuthAuthorizationRequiredError):
        await _Harness().client.access_token("example", "user-1")

    assert server.requests == []


async def test_access_token_expired_without_refresh_token_expect_required(
    server: _Server,
) -> None:
    """An expired token with no refresh token requires a new sign-in."""
    harness = _Harness()
    await harness.hold(expires_in=0, refresh_token=None)

    with pytest.raises(OAuthAuthorizationRequiredError):
        await harness.client.access_token("example", "user-1")

    assert server.requests == []


@pytest.mark.parametrize("status", [400, 401])
async def test_access_token_with_invalid_grant_expect_required_and_tokens_kept(
    server: _Server,
    status: int,
) -> None:
    """A dead refresh token requires sign-in; stored tokens are left for revoke."""
    harness = _Harness()
    held = await harness.hold(expires_in=0)
    server.replies = [httpx.Response(status, json={"error": "invalid_grant"})]

    with pytest.raises(OAuthAuthorizationRequiredError):
        await harness.client.access_token("example", "user-1")

    assert await harness.tokens.load(_KEY) == held


async def test_access_token_with_request_level_rejection_expect_tokens_kept(
    server: _Server,
) -> None:
    """A 400 that is not invalid_grant never costs the subject its refresh token."""
    harness = _Harness()
    held = await harness.hold(expires_in=0)
    server.replies = [httpx.Response(400, json={"error": "invalid_target"})]

    with pytest.raises(OAuthTokenEndpointError):
        await harness.client.access_token("example", "user-1")

    assert await harness.tokens.load(_KEY) == held


async def test_access_token_rotated_by_another_instance_expect_its_token(
    server: _Server,
) -> None:
    """A grant rejected because another instance rotated first reuses its token."""
    store = _SwappingTokenStore(
        _tokens(access_token="access-7", refresh_token="refresh-7")
    )
    harness = _Harness(token_store=store)
    await harness.hold(expires_in=0)
    server.replies = [httpx.Response(400, json={"error": "invalid_grant"})]

    token = await harness.client.access_token("example", "user-1")

    stored = await harness.tokens.load(_KEY)
    assert token == "access-7"
    assert stored is not None
    assert stored.refresh_token == SecretStr("refresh-7")


async def test_access_token_rejected_with_expired_replacement_expect_required(
    server: _Server,
) -> None:
    """A replacement that is itself unusable does not mask the rejected grant."""
    store = _SwappingTokenStore(_tokens(access_token="access-7", expires_in=0))
    harness = _Harness(token_store=store)
    await harness.hold(expires_in=0)
    server.replies = [httpx.Response(400, json={"error": "invalid_grant"})]

    with pytest.raises(OAuthAuthorizationRequiredError):
        await harness.client.access_token("example", "user-1")

    stored = await harness.tokens.load(_KEY)
    assert stored is not None
    assert stored.access_token == SecretStr("access-7")


async def test_access_token_signed_out_during_refresh_expect_not_restored(
    server: _Server,
) -> None:
    """A sign-out that lands during a refresh is not undone by its response."""
    harness = _Harness(token_store=_SwappingTokenStore(None))
    await harness.hold(expires_in=0)
    server.replies = [_token_reply()]

    with pytest.raises(OAuthAuthorizationRequiredError):
        await harness.client.access_token("example", "user-1")

    assert await harness.tokens.load(_KEY) is None


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (httpx.Response(500), OAuthTokenEndpointError),
        (httpx.ConnectError("refused"), OAuthTransportError),
        (_token_reply(access_token=None), OAuthTokenResponseError),
    ],
)
async def test_access_token_refresh_failure_expect_tokens_kept(
    server: _Server,
    reply: _Reply,
    expected: type[AbstractSpakkyOAuthError],
) -> None:
    """A transient refresh failure keeps the stored tokens for a later attempt."""
    harness = _Harness()
    held = await harness.hold(expires_in=0)
    server.replies = [reply]

    with pytest.raises(expected):
        await harness.client.access_token("example", "user-1")

    assert await harness.tokens.load(_KEY) == held


async def test_revoke_expect_refresh_token_revoked_and_tokens_removed(
    server: _Server,
) -> None:
    """Sign-out removes local tokens and revokes the refresh token."""
    harness = _Harness()
    await harness.hold()
    server.replies = [httpx.Response(200)]

    await harness.client.revoke("example", "user-1")

    assert str(server.requests[0].url) == "https://auth.example.test/revoke"
    assert server.form() == {
        "token": "refresh-1",
        "token_type_hint": "refresh_token",
        "client_id": "my-app",
    }
    assert await harness.tokens.load(_KEY) is None


async def test_revoke_without_refresh_token_expect_access_token_revoked(
    server: _Server,
) -> None:
    """Without a refresh token the access token itself is revoked."""
    harness = _Harness()
    await harness.hold(refresh_token=None)
    server.replies = [httpx.Response(200)]

    await harness.client.revoke("example", "user-1")

    assert server.form()["token"] == "access-1"
    assert server.form()["token_type_hint"] == "access_token"


async def test_revoke_without_revocation_endpoint_expect_local_removal_only(
    server: _Server,
) -> None:
    """A server without revocation still signs the subject out locally."""
    harness = _Harness(_registration(revocation_endpoint=None))
    await harness.hold()

    await harness.client.revoke("example", "user-1")

    assert server.requests == []
    assert await harness.tokens.load(_KEY) is None


async def test_revoke_without_tokens_expect_no_request(server: _Server) -> None:
    """Revoking a subject that holds nothing is a no-op."""
    await _Harness().client.revoke("example", "user-1")

    assert server.requests == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (httpx.Response(503), OAuthRevocationError),
        (httpx.ConnectError("refused"), OAuthRevocationError),
    ],
)
async def test_revoke_unconfirmed_by_server_expect_error_after_local_removal(
    server: _Server,
    reply: _Reply,
    expected: type[AbstractSpakkyOAuthError],
) -> None:
    """An unconfirmed revocation is reported, but the subject is signed out here."""
    harness = _Harness()
    await harness.hold()
    server.replies = [reply]

    with pytest.raises(expected):
        await harness.client.revoke("example", "user-1")

    assert await harness.tokens.load(_KEY) is None


async def test_revoke_for_unknown_client_expect_not_configured() -> None:
    """Revocation needs a configured registration."""
    with pytest.raises(OAuthClientNotConfiguredError):
        await _Harness().client.revoke("missing", "user-1")


@pytest.mark.parametrize("name", ["state", "scope", "nonce", "redirect_uri"])
async def test_begin_authorization_with_protocol_parameter_expect_request_error(
    name: str,
) -> None:
    """Per-request parameters cannot replace fields the client controls."""
    harness = _Harness()

    with pytest.raises(OAuthAuthorizationRequestError):
        await harness.client.begin_authorization(
            "example",
            "user-1",
            _REDIRECT,
            parameters={name: "attacker-chosen"},
        )


async def test_begin_authorization_with_blank_client_id_expect_request_error() -> None:
    """A blank client id override is refused instead of sent."""
    with pytest.raises(OAuthAuthorizationRequestError):
        await _Harness().client.begin_authorization(
            "example",
            "user-1",
            _REDIRECT,
            client_id=" ",
        )


async def test_complete_authorization_with_blank_client_id_expect_state_kept(
    server: _Server,
) -> None:
    """A blank callback client id is refused before the state is consumed."""
    harness = _Harness()
    request = await harness.client.begin_authorization("example", "user-1", _REDIRECT)

    with pytest.raises(OAuthAuthorizationRequestError):
        await harness.client.complete_authorization(
            request.state,
            "code-1",
            client_id="",
        )

    assert await harness.states.take(request.state) is not None
    assert server.requests == []


async def test_access_token_with_non_ascii_rejected_token_expect_current_token(
    server: _Server,
) -> None:
    """A rejected token that is not ASCII is compared, not crashed on."""
    harness = _Harness()
    await harness.hold()

    token = await harness.client.access_token(
        "example",
        "user-1",
        rejected_token="토큰",
    )

    assert token == "access-1"
    assert server.requests == []


async def test_refresh_with_string_lifetime_expect_expiry_parsed(
    server: _Server,
) -> None:
    """Servers that send expires_in as a numeric string still rotate cleanly."""
    harness = _Harness()
    await harness.hold(expires_in=0)
    server.replies = [_token_reply(expires_in="1800")]

    await harness.client.access_token("example", "user-1")

    stored = await harness.tokens.load(_KEY)
    assert stored is not None
    assert stored.expires_at == _NOW + timedelta(seconds=1800)
    assert stored.refresh_token == SecretStr("refresh-2")


async def test_token_endpoint_with_invalid_port_expect_transport_error() -> None:
    """An endpoint httpx cannot address surfaces as a transport failure."""
    registration = _registration().model_copy(
        update={"token_endpoint": "https://auth.example.test:99999/token"}
    )
    harness = _Harness(registration)
    await harness.hold(expires_in=0)

    with pytest.raises(OAuthTransportError):
        await harness.client.access_token("example", "user-1")
