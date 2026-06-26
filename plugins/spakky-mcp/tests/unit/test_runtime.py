"""Tests for runtime MCP server resolution."""

import pytest

from spakky.agent import RunAgentInput
from spakky.plugins.mcp import (
    MCP_METADATA_KEY,
    MCP_SERVERS_METADATA_KEY,
    McpConfig,
    McpRuntimeServerResolver,
    McpServerConfig,
)
from spakky.plugins.mcp.error import McpServerConfigurationError


def _config() -> McpConfig:
    config = McpConfig()
    config.servers = (
        McpServerConfig(name="weather", command="weather-mcp"),
        McpServerConfig(name="github", command="github-mcp"),
    )
    return config


def test_runtime_resolver_uses_configured_servers_without_run_input() -> None:
    """No runtime selector means all configured servers are joined."""
    resolver = McpRuntimeServerResolver(_config())

    assert tuple(
        server.name for server in resolver.resolve_servers(object(), None)
    ) == (
        "weather",
        "github",
    )


def test_runtime_resolver_uses_run_metadata_server_names() -> None:
    """Run metadata selects a subset of configured MCP servers."""
    resolver = McpRuntimeServerResolver(_config())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: {MCP_SERVERS_METADATA_KEY: ["github"]}},
    )

    resolved = resolver.resolve_servers(object(), run_input)

    assert tuple(server.name for server in resolved) == ("github",)


def test_runtime_resolver_rejects_duplicate_configured_server_names() -> None:
    """Duplicate configured names cannot fall through to ambiguous tool prefixes."""
    config = McpConfig()
    config.servers = (
        McpServerConfig(name="github", command="github-mcp"),
        McpServerConfig(name="github", command="other-github-mcp"),
    )
    resolver = McpRuntimeServerResolver(config)

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), None)


def test_runtime_resolver_rejects_duplicate_runtime_server_names() -> None:
    """Runtime selectors cannot attach the same external MCP server name twice."""
    resolver = McpRuntimeServerResolver(_config())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: {MCP_SERVERS_METADATA_KEY: ["github", "github"]}},
    )

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), run_input)


def test_runtime_resolver_rejects_inline_name_conflicting_with_config() -> None:
    """Inline declarations cannot shadow configured MCP server identities."""
    resolver = McpRuntimeServerResolver(_config())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={
            MCP_METADATA_KEY: {
                MCP_SERVERS_METADATA_KEY: [
                    {"name": "github", "command": "tenant-github-mcp"},
                ]
            }
        },
    )

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), run_input)


def test_runtime_resolver_uses_configured_servers_when_metadata_has_no_servers() -> (
    None
):
    """An mcp metadata object without servers still falls back to configured servers."""
    resolver = McpRuntimeServerResolver(_config())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: {}},
    )

    assert tuple(
        server.name for server in resolver.resolve_servers(object(), run_input)
    ) == ("weather", "github")


def test_runtime_resolver_accepts_inline_server_declarations() -> None:
    """User/service settings may provide inline MCP server declarations per run."""
    resolver = McpRuntimeServerResolver(McpConfig())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={
            MCP_METADATA_KEY: {
                MCP_SERVERS_METADATA_KEY: [
                    {"name": "linear", "command": "linear-mcp"},
                ]
            }
        },
    )

    resolved = resolver.resolve_servers(object(), run_input)

    assert len(resolved) == 1
    assert resolved[0].name == "linear"
    assert resolved[0].command == "linear-mcp"


def test_runtime_resolver_rejects_non_object_mcp_metadata() -> None:
    """Run MCP metadata must be an object."""
    resolver = McpRuntimeServerResolver(McpConfig())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: "weather"},
    )

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), run_input)


def test_runtime_resolver_rejects_non_array_server_metadata() -> None:
    """Run MCP servers metadata must be an array of names or declarations."""
    resolver = McpRuntimeServerResolver(McpConfig())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: {MCP_SERVERS_METADATA_KEY: "weather"}},
    )

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), run_input)


def test_runtime_resolver_rejects_invalid_server_entry() -> None:
    """Every runtime server entry must be a configured name or inline object."""
    resolver = McpRuntimeServerResolver(McpConfig())
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={MCP_METADATA_KEY: {MCP_SERVERS_METADATA_KEY: [3]}},
    )

    with pytest.raises(McpServerConfigurationError):
        resolver.resolve_servers(object(), run_input)
