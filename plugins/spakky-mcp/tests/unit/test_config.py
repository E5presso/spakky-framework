"""Unit tests for MCP client configuration."""

import pytest

from spakky.plugins.mcp.config import (
    McpOAuthClientAuthMethod,
    McpOAuthClientCredentialsConfig,
    McpConfig,
    McpServerAuthConfig,
    McpServerConfig,
    McpToolServerConfig,
    McpTransport,
)
from spakky.plugins.mcp.constants import (
    DEFAULT_MCP_CALL_TIMEOUT_SECONDS,
    DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MCP_SERVER_NAME,
)
from spakky.plugins.mcp.error import McpServerConfigurationError


def test_config_defaults_to_no_servers() -> None:
    """Default config declares no servers and uses the default connect timeout."""
    config = McpConfig()

    assert config.servers == ()
    assert config.connect_timeout_seconds == DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS


def test_config_defaults_tool_server_to_default_identity() -> None:
    """Default config exposes the default tool-server name over stdio."""
    config = McpConfig()

    assert config.tool_server.name == DEFAULT_MCP_SERVER_NAME
    assert config.tool_server.transport is McpTransport.STDIO


def test_tool_server_name_cannot_be_blank() -> None:
    """A blank tool-server name cannot front the protocol handshake."""
    with pytest.raises(McpServerConfigurationError):
        McpToolServerConfig(name="   ")


def test_tool_server_accepts_named_identity_and_transport() -> None:
    """An explicit tool-server identity and transport are retained."""
    tool_server = McpToolServerConfig(
        name="my-agent",
        transport=McpTransport.STREAMABLE_HTTP,
    )

    assert tool_server.name == "my-agent"
    assert tool_server.transport is McpTransport.STREAMABLE_HTTP


def test_stdio_server_uses_default_call_timeout() -> None:
    """A stdio server declaration defaults its per-call timeout."""
    server = McpServerConfig(name="weather", command="run-server")

    assert server.transport is McpTransport.STDIO
    assert server.call_timeout_seconds == DEFAULT_MCP_CALL_TIMEOUT_SECONDS


def test_stdio_server_requires_command() -> None:
    """A stdio server without a command cannot be dialed."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(name="weather", transport=McpTransport.STDIO)


def test_streamable_http_server_requires_http_url() -> None:
    """A streamable_http server requires an http(s) url."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(
            name="weather",
            transport=McpTransport.STREAMABLE_HTTP,
            url="ftp://example.invalid",
        )


def test_streamable_http_server_accepts_https_url() -> None:
    """A streamable_http server accepts an https url."""
    server = McpServerConfig(
        name="weather",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://example.test/mcp",
    )

    assert server.url == "https://example.test/mcp"


def test_streamable_http_server_accepts_static_auth_headers() -> None:
    """A remote MCP server can declare static HTTP auth headers."""
    server = McpServerConfig(
        name="github",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.test",
        auth=McpServerAuthConfig(headers={"X-Api-Key": "secret"}),
    )

    assert server.auth.headers == {"X-Api-Key": "secret"}


def test_streamable_http_server_accepts_bearer_token_env() -> None:
    """A remote MCP server can resolve bearer auth from an env var at connect time."""
    server = McpServerConfig(
        name="github",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.test",
        auth=McpServerAuthConfig(bearer_token_env="GITHUB_MCP_TOKEN"),
    )

    assert server.auth.bearer_token_env == "GITHUB_MCP_TOKEN"


def test_streamable_http_server_accepts_oauth_client_credentials() -> None:
    """A remote MCP server can declare OAuth2 client-credentials auth."""
    server = McpServerConfig(
        name="linear",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.test",
        auth=McpServerAuthConfig(
            oauth_client_credentials=McpOAuthClientCredentialsConfig(
                token_url="https://auth.example.test/oauth/token",
                client_id_env="LINEAR_CLIENT_ID",
                client_secret_env="LINEAR_CLIENT_SECRET",
                scopes=("mcp:tools",),
                client_auth_method=McpOAuthClientAuthMethod.CLIENT_SECRET_POST,
            )
        ),
    )

    oauth = server.auth.oauth_client_credentials
    assert oauth is not None
    assert oauth.token_url == "https://auth.example.test/oauth/token"
    assert oauth.scopes == ("mcp:tools",)


def test_oauth_client_credentials_rejects_non_http_token_url() -> None:
    """OAuth token acquisition requires an HTTP(S) token endpoint."""
    with pytest.raises(McpServerConfigurationError):
        McpOAuthClientCredentialsConfig(
            token_url="ftp://auth.example.test/oauth/token",
            client_id="client",
            client_secret="secret",
        )


def test_oauth_client_credentials_rejects_blank_optional_text() -> None:
    """Blank optional OAuth text values are configuration errors."""
    with pytest.raises(McpServerConfigurationError):
        McpOAuthClientCredentialsConfig(
            token_url="https://auth.example.test/oauth/token",
            client_id=" ",
            client_secret="secret",
        )


def test_oauth_client_credentials_rejects_blank_scope() -> None:
    """Blank OAuth scopes cannot be serialized into a token request."""
    with pytest.raises(McpServerConfigurationError):
        McpOAuthClientCredentialsConfig(
            token_url="https://auth.example.test/oauth/token",
            client_id="client",
            client_secret="secret",
            scopes=("tools:read", " "),
        )


def test_server_auth_rejects_bearer_and_oauth_together() -> None:
    """Bearer-token auth and OAuth token acquisition cannot both own Authorization."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(
            bearer_token_env="GITHUB_MCP_TOKEN",
            oauth_client_credentials=McpOAuthClientCredentialsConfig(
                token_url="https://auth.example.test/oauth/token",
                client_id="client",
                client_secret="secret",
            ),
        )


def test_oauth_client_credentials_requires_client_identity() -> None:
    """OAuth client credentials require a configured client id source."""
    with pytest.raises(McpServerConfigurationError):
        McpOAuthClientCredentialsConfig(
            token_url="https://auth.example.test/oauth/token",
            client_secret="secret",
        )


def test_oauth_client_credentials_requires_client_secret() -> None:
    """OAuth client credentials require a configured client secret source."""
    with pytest.raises(McpServerConfigurationError):
        McpOAuthClientCredentialsConfig(
            token_url="https://auth.example.test/oauth/token",
            client_id="client",
        )


def test_server_auth_rejects_blank_header_values() -> None:
    """HTTP auth headers cannot hide missing names or values."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(headers={"X-Api-Key": " "})


def test_server_auth_rejects_multiline_headers() -> None:
    """HTTP auth headers cannot smuggle newline-delimited header content."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(headers={"X-Api-Key": "secret\nsecond"})


def test_server_auth_rejects_blank_bearer_source() -> None:
    """Blank bearer token sources fail before connection setup."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(bearer_token_env=" ")


def test_server_auth_rejects_dual_bearer_sources() -> None:
    """Bearer auth must have exactly one literal or env-backed source."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(
            bearer_token="token",
            bearer_token_env="GITHUB_MCP_TOKEN",
        )


def test_server_auth_rejects_authorization_header_with_token_owner() -> None:
    """Static Authorization cannot be combined with generated bearer auth."""
    with pytest.raises(McpServerConfigurationError):
        McpServerAuthConfig(
            headers={"Authorization": "Bearer static"},
            bearer_token="dynamic",
        )


def test_stdio_server_rejects_auth_config() -> None:
    """HTTP auth config is invalid for stdio MCP server declarations."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(
            name="local",
            command="local-mcp",
            auth=McpServerAuthConfig(headers={"X-Api-Key": "secret"}),
        )


def test_server_name_cannot_be_blank() -> None:
    """A blank server name cannot prefix tool names."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(name="   ", command="run-server")


def test_server_name_cannot_contain_separator() -> None:
    """A server name embedding the tool name separator breaks prefixing."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(name="we__ather", command="run-server")


def test_server_call_timeout_must_be_positive() -> None:
    """A non-positive call timeout cannot bound an invocation."""
    with pytest.raises(McpServerConfigurationError):
        McpServerConfig(name="weather", command="run-server", call_timeout_seconds=0)


def test_server_accepts_explicit_positive_call_timeout() -> None:
    """An explicit positive call timeout is retained on the server config."""
    server = McpServerConfig(
        name="weather",
        command="run-server",
        call_timeout_seconds=12.5,
    )

    assert server.call_timeout_seconds == 12.5


def test_config_rejects_duplicate_server_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured MCP server names must be globally unique."""
    monkeypatch.setenv(
        "SPAKKY_MCP__SERVERS",
        '[{"name": "github", "command": "github-mcp"},'
        ' {"name": "github", "command": "other-github-mcp"}]',
    )

    with pytest.raises(McpServerConfigurationError):
        McpConfig()


def test_server_by_name_returns_declared_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """server_by_name returns the matching declared server."""
    monkeypatch.setenv(
        "SPAKKY_MCP__SERVERS",
        '[{"name": "weather", "command": "weather-server"},'
        ' {"name": "calc", "command": "calc-server"}]',
    )
    config = McpConfig()

    assert config.server_by_name("calc").command == "calc-server"


def test_server_by_name_rejects_unknown_server() -> None:
    """server_by_name fails when the requested server is not declared."""
    config = McpConfig()

    with pytest.raises(McpServerConfigurationError):
        config.server_by_name("missing")


def test_config_reads_servers_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Servers declared via the SPAKKY_MCP__ env prefix load as typed config."""
    monkeypatch.setenv(
        "SPAKKY_MCP__SERVERS",
        '[{"name": "weather", "command": "weather-server"}]',
    )

    config = McpConfig()

    assert len(config.servers) == 1
    assert config.servers[0].name == "weather"
    assert config.servers[0].command == "weather-server"
