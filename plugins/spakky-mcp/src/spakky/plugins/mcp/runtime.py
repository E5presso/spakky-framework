"""Runtime MCP connection resolution for user/service supplied toolsets."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from spakky.agent import RunAgentInput
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.mcp.config import (
    McpConfig,
    McpServerConfig,
    validate_unique_server_names,
)
from spakky.plugins.mcp.error import McpServerConfigurationError

MCP_METADATA_KEY = "mcp"
"""RunAgentInput.metadata key carrying runtime MCP connection selectors."""

MCP_SERVERS_METADATA_KEY = "servers"
"""Nested metadata key carrying server names or inline server declarations."""


class IMcpRuntimeServerResolver(ABC):
    """Resolve MCP servers to join for one Agent run."""

    @abstractmethod
    def resolve_servers(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None,
    ) -> tuple[McpServerConfig, ...]:
        """Return the MCP server configs selected for this run."""
        ...


@Pod()
class McpRuntimeServerResolver(IMcpRuntimeServerResolver):
    """Default resolver using configured servers plus RunAgentInput metadata."""

    def __init__(self, config: McpConfig) -> None:
        self._config = config

    def resolve_servers(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None,
    ) -> tuple[McpServerConfig, ...]:
        """Resolve runtime metadata or all configured servers."""
        _ = agent_instance
        runtime_servers = _runtime_servers_from_input(run_input)
        if runtime_servers is None:
            return validate_unique_server_names(self._config.servers)
        return validate_unique_server_names(
            tuple(self._runtime_server(item) for item in runtime_servers)
        )

    def _runtime_server(self, item: object) -> McpServerConfig:
        """Resolve one runtime server selector or inline declaration."""
        if isinstance(item, str):
            return self._config.server_by_name(item)
        if isinstance(item, Mapping):
            server = McpServerConfig.model_validate(dict(item))
            if server.name in _configured_server_names(self._config):
                raise McpServerConfigurationError(
                    "Runtime MCP server name conflicts with configured server"
                )
            return server
        raise McpServerConfigurationError("Runtime MCP server entry is invalid")


def _runtime_servers_from_input(
    run_input: RunAgentInput | None,
) -> tuple[object, ...] | None:
    """Extract runtime MCP server declarations from run metadata."""
    if run_input is None:
        return None
    mcp = run_input.metadata.get(MCP_METADATA_KEY)
    if mcp is None:
        return None
    if not isinstance(mcp, Mapping):
        raise McpServerConfigurationError("Run MCP metadata must be an object")
    servers = mcp.get(MCP_SERVERS_METADATA_KEY)
    if servers is None:
        return None
    if not isinstance(servers, tuple | list):
        raise McpServerConfigurationError("Run MCP servers metadata must be an array")
    return tuple(servers)


def _configured_server_names(config: McpConfig) -> set[str]:
    """Return configured server names reserved for static declarations."""
    return {server.name for server in config.servers}
