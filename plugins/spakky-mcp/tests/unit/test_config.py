"""Unit tests for MCP client configuration."""

import pytest

from spakky.plugins.mcp.config import (
    McpConfig,
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
