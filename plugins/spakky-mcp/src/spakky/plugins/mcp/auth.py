"""HTTP authentication helpers for remote MCP servers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from os import environ
from typing import cast

import httpx
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.mcp.config import (
    McpOAuthClientAuthMethod,
    McpOAuthClientCredentialsConfig,
    McpServerAuthConfig,
    McpServerConfig,
    McpTransport,
)
from spakky.plugins.mcp.error import McpServerConfigurationError, McpTransportError

ACCESS_TOKEN_KEY = "access_token"
"""OAuth token response field carrying the bearer token."""


class IMcpHttpClientProvider(ABC):
    """Factory for authenticated HTTP clients used by streamable_http MCP servers."""

    @abstractmethod
    def open_client(
        self,
        server: McpServerConfig,
    ) -> AbstractAsyncContextManager[httpx.AsyncClient | None]:
        """Open an optional HTTP client for one server connection."""
        ...


@Pod()
class McpHttpClientProvider(IMcpHttpClientProvider):
    """Default declarative HTTP auth provider for remote MCP servers."""

    @asynccontextmanager
    async def open_client(
        self,
        server: McpServerConfig,
    ) -> AsyncGenerator[httpx.AsyncClient | None, None]:
        """Yield a configured HTTP client when the server declares auth headers."""
        if server.transport is not McpTransport.STREAMABLE_HTTP:
            yield None
            return
        headers = await resolve_http_auth_headers(server.auth)
        if not headers:
            yield None
            return
        async with httpx.AsyncClient(headers=headers) as client:
            yield client


async def resolve_http_auth_headers(
    auth: McpServerAuthConfig,
    env: Mapping[str, str] = environ,
) -> dict[str, str]:
    """Return HTTP headers for an authenticated streamable_http MCP connection."""
    headers = dict(auth.headers)
    if auth.bearer_token is not None or auth.bearer_token_env is not None:
        token = _resolve_secret(
            value=auth.bearer_token,
            env_name=auth.bearer_token_env,
            env=env,
            label="MCP bearer token",
        )
        headers["Authorization"] = f"Bearer {token}"
        return headers
    if auth.oauth_client_credentials is not None:
        token = await _fetch_oauth_client_credentials_token(
            auth.oauth_client_credentials,
            env,
        )
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _fetch_oauth_client_credentials_token(
    config: McpOAuthClientCredentialsConfig,
    env: Mapping[str, str],
) -> str:
    """Fetch one OAuth2 client-credentials access token."""
    client_id = _resolve_secret(
        value=config.client_id,
        env_name=config.client_id_env,
        env=env,
        label="MCP OAuth client id",
    )
    client_secret = _resolve_secret(
        value=config.client_secret,
        env_name=config.client_secret_env,
        env=env,
        label="MCP OAuth client secret",
    )
    data = _oauth_token_request_data(config, client_id, client_secret)
    auth: tuple[str, str] | None = None
    if config.client_auth_method is McpOAuthClientAuthMethod.CLIENT_SECRET_BASIC:
        auth = (client_id, client_secret)
    try:
        async with httpx.AsyncClient() as client:
            if auth is None:
                response = await client.post(config.token_url, data=data)
            else:
                response = await client.post(config.token_url, data=data, auth=auth)
        response.raise_for_status()
        payload = cast(dict[str, object], response.json())
    except httpx.HTTPError as e:
        raise McpTransportError("MCP OAuth token request failed") from e
    except ValueError as e:
        raise McpTransportError("MCP OAuth token response is not JSON") from e
    token = payload.get(ACCESS_TOKEN_KEY)
    if not isinstance(token, str) or not token.strip():
        raise McpTransportError("MCP OAuth token response has no access_token")
    return token


def _oauth_token_request_data(
    config: McpOAuthClientCredentialsConfig,
    client_id: str,
    client_secret: str,
) -> dict[str, str]:
    """Build the form body for a token request."""
    data = {
        "grant_type": "client_credentials",
        **config.extra_token_params,
    }
    if config.scopes:
        data["scope"] = " ".join(config.scopes)
    if config.audience is not None:
        data["audience"] = config.audience
    if config.client_auth_method is McpOAuthClientAuthMethod.CLIENT_SECRET_POST:
        data["client_id"] = client_id
        data["client_secret"] = client_secret
    return data


def _resolve_secret(
    *,
    value: str | None,
    env_name: str | None,
    env: Mapping[str, str],
    label: str,
) -> str:
    """Resolve a configured secret literal or env var."""
    if value is not None:
        return value
    if env_name is not None:
        resolved = env.get(env_name)
        if resolved is not None and resolved.strip():
            return resolved
    raise McpServerConfigurationError(f"{label} is not configured")
