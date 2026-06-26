"""Tests for remote MCP HTTP authentication helpers."""

from collections.abc import Mapping

import httpx
import pytest

from spakky.plugins.mcp import (
    McpHttpClientProvider,
    McpOAuthClientAuthMethod,
    McpOAuthClientCredentialsConfig,
    McpServerAuthConfig,
    McpServerConfig,
    McpTransport,
    resolve_http_auth_headers,
)
from spakky.plugins.mcp import auth as auth_module
from spakky.plugins.mcp.error import McpServerConfigurationError, McpTransportError


class _FakeResponse:
    """Small HTTP response double for OAuth token exchange tests."""

    def __init__(
        self,
        payload: Mapping[str, object] | None = None,
        json_error: bool = False,
        status_error: httpx.HTTPError | None = None,
    ) -> None:
        self._payload = dict(payload or {})
        self._json_error = json_error
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error

    def json(self) -> Mapping[str, object]:
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _FakeAsyncClient:
    """AsyncClient double recording OAuth token requests."""

    response = _FakeResponse({"access_token": "oauth-token"})
    post_error: httpx.HTTPError | None = None
    post_calls: list[tuple[str, Mapping[str, str], tuple[str, str] | None]] = []

    def __init__(self, headers: Mapping[str, str] | None = None) -> None:
        self.headers = dict(headers or {})

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(
        self,
        url: str,
        data: Mapping[str, str],
        auth: tuple[str, str] | None = None,
    ) -> _FakeResponse:
        self.post_calls.append((url, dict(data), auth))
        if self.post_error is not None:
            raise self.post_error
        return self.response


def _patch_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncClient.response = _FakeResponse({"access_token": "oauth-token"})
    _FakeAsyncClient.post_error = None
    _FakeAsyncClient.post_calls = []
    monkeypatch.setattr(auth_module.httpx, "AsyncClient", _FakeAsyncClient)


async def test_http_client_provider_returns_none_for_stdio_server() -> None:
    """stdio MCP servers do not receive an HTTP client."""
    server = McpServerConfig(name="local", command="local-mcp")

    async with McpHttpClientProvider().open_client(server) as client:
        assert client is None


async def test_http_client_provider_returns_none_for_unauthenticated_http() -> None:
    """streamable_http servers without auth use the SDK default HTTP client."""
    server = McpServerConfig(
        name="public",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://example.test/mcp",
    )

    async with McpHttpClientProvider().open_client(server) as client:
        assert client is None


async def test_resolve_http_auth_headers_accepts_direct_bearer_token() -> None:
    """A direct bearer token becomes the Authorization header."""
    headers = await resolve_http_auth_headers(
        McpServerAuthConfig(headers={"X-Mcp-Tenant": "tenant-1"}, bearer_token="token")
    )

    assert headers == {
        "X-Mcp-Tenant": "tenant-1",
        "Authorization": "Bearer token",
    }


async def test_resolve_http_auth_headers_rejects_missing_env_secret() -> None:
    """Missing env-backed secrets fail before an MCP connection is opened."""
    with pytest.raises(McpServerConfigurationError):
        await resolve_http_auth_headers(
            McpServerAuthConfig(bearer_token_env="MISSING_MCP_TOKEN"),
            env={},
        )


def test_resolve_secret_rejects_missing_literal_and_env() -> None:
    """The low-level secret resolver rejects absent literal and env sources."""
    with pytest.raises(McpServerConfigurationError):
        auth_module._resolve_secret(
            value=None,
            env_name=None,
            env={},
            label="MCP test secret",
        )


async def test_resolve_http_auth_headers_fetches_oauth_client_credentials_basic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAuth client_secret_basic fetches a token and sends client auth separately."""
    _patch_http_client(monkeypatch)
    headers = await resolve_http_auth_headers(
        McpServerAuthConfig(
            oauth_client_credentials=McpOAuthClientCredentialsConfig(
                token_url="https://auth.example.test/token",
                client_id="client-id",
                client_secret="client-secret",
                scopes=("tools:read",),
                audience="mcp-api",
                extra_token_params={"resource": "spakky"},
            )
        )
    )

    assert headers == {"Authorization": "Bearer oauth-token"}
    assert _FakeAsyncClient.post_calls == [
        (
            "https://auth.example.test/token",
            {
                "grant_type": "client_credentials",
                "scope": "tools:read",
                "audience": "mcp-api",
                "resource": "spakky",
            },
            ("client-id", "client-secret"),
        )
    ]


async def test_resolve_http_auth_headers_fetches_oauth_client_credentials_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAuth client_secret_post sends client credentials in the form body."""
    _patch_http_client(monkeypatch)
    headers = await resolve_http_auth_headers(
        McpServerAuthConfig(
            oauth_client_credentials=McpOAuthClientCredentialsConfig(
                token_url="https://auth.example.test/token",
                client_id_env="MCP_CLIENT_ID",
                client_secret_env="MCP_CLIENT_SECRET",
                client_auth_method=McpOAuthClientAuthMethod.CLIENT_SECRET_POST,
            )
        ),
        env={"MCP_CLIENT_ID": "id-env", "MCP_CLIENT_SECRET": "secret-env"},
    )

    assert headers == {"Authorization": "Bearer oauth-token"}
    assert _FakeAsyncClient.post_calls == [
        (
            "https://auth.example.test/token",
            {
                "grant_type": "client_credentials",
                "client_id": "id-env",
                "client_secret": "secret-env",
            },
            None,
        )
    ]


async def test_resolve_http_auth_headers_wraps_oauth_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token endpoint HTTP failures surface as MCP transport errors."""
    _patch_http_client(monkeypatch)
    _FakeAsyncClient.post_error = httpx.ConnectError(
        "down",
        request=httpx.Request("POST", "https://auth.example.test/token"),
    )

    with pytest.raises(McpTransportError):
        await resolve_http_auth_headers(
            McpServerAuthConfig(
                oauth_client_credentials=McpOAuthClientCredentialsConfig(
                    token_url="https://auth.example.test/token",
                    client_id="client-id",
                    client_secret="client-secret",
                )
            )
        )


async def test_resolve_http_auth_headers_wraps_oauth_json_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-JSON token responses surface as MCP transport errors."""
    _patch_http_client(monkeypatch)
    _FakeAsyncClient.response = _FakeResponse(json_error=True)

    with pytest.raises(McpTransportError):
        await resolve_http_auth_headers(
            McpServerAuthConfig(
                oauth_client_credentials=McpOAuthClientCredentialsConfig(
                    token_url="https://auth.example.test/token",
                    client_id="client-id",
                    client_secret="client-secret",
                )
            )
        )


async def test_resolve_http_auth_headers_rejects_oauth_response_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAuth token responses must include a non-blank access_token."""
    _patch_http_client(monkeypatch)
    _FakeAsyncClient.response = _FakeResponse({"access_token": " "})

    with pytest.raises(McpTransportError):
        await resolve_http_auth_headers(
            McpServerAuthConfig(
                oauth_client_credentials=McpOAuthClientCredentialsConfig(
                    token_url="https://auth.example.test/token",
                    client_id="client-id",
                    client_secret="client-secret",
                )
            )
        )
