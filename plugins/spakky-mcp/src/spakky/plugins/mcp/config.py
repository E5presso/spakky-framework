"""Configuration for the spakky-mcp adapter (external clients and tool server)."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.mcp.constants import (
    DEFAULT_MCP_CALL_TIMEOUT_SECONDS,
    DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MCP_SERVER_NAME,
    MCP_TOOL_NAME_SEPARATOR,
    SPAKKY_MCP_CONFIG_ENV_PREFIX,
)
from spakky.plugins.mcp.error import McpServerConfigurationError


class McpTransport(StrEnum):
    """Transport an external MCP server is reached over."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class McpServerConfig(BaseModel):
    """Declaration of one external MCP server the agent consumes tools from."""

    name: str
    transport: McpTransport = McpTransport.STDIO
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    call_timeout_seconds: float = DEFAULT_MCP_CALL_TIMEOUT_SECONDS

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Reject server names that cannot prefix tool names deterministically."""
        if not value.strip():
            raise McpServerConfigurationError("MCP server name cannot be blank")
        if MCP_TOOL_NAME_SEPARATOR in value:
            raise McpServerConfigurationError(
                "MCP server name cannot contain the tool name separator"
            )
        return value

    @field_validator("call_timeout_seconds")
    @classmethod
    def _validate_call_timeout(cls, value: float) -> float:
        """Reject non-positive call timeouts that cannot bound an invocation."""
        if value <= 0:
            raise McpServerConfigurationError(
                "MCP server call timeout must be positive"
            )
        return value

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> "McpServerConfig":
        """Require the connection field each transport needs to dial the server."""
        if self.transport is McpTransport.STDIO and not self.command:
            raise McpServerConfigurationError("MCP stdio server requires a command")
        if self.transport is McpTransport.STREAMABLE_HTTP and not _is_http_url(
            self.url
        ):
            raise McpServerConfigurationError(
                "MCP streamable_http server requires an http(s) url"
            )
        return self


def _is_http_url(url: str | None) -> bool:
    return url is not None and (url.startswith("http://") or url.startswith("https://"))


class McpToolServerConfig(BaseModel):
    """Declaration of how this agent exposes its own tools as an MCP server."""

    name: str = DEFAULT_MCP_SERVER_NAME
    transport: McpTransport = McpTransport.STDIO

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Reject a blank server identity that cannot front the protocol handshake."""
        if not value.strip():
            raise McpServerConfigurationError("MCP server name cannot be blank")
        return value


@Configuration()
class McpConfig(BaseSettings):
    """Settings declaring the external MCP servers an agent consumes."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_MCP_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    servers: tuple[McpServerConfig, ...] = ()
    """External MCP servers whose tools join the agent tool catalog."""

    connect_timeout_seconds: float = DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS
    """Timeout budget for establishing an MCP server connection."""

    tool_server: McpToolServerConfig = McpToolServerConfig()
    """Identity and transport this agent advertises when exposing its own tools."""

    def __init__(self) -> None:
        super().__init__()

    def server_by_name(self, name: str) -> McpServerConfig:
        """Return the declared server with the given name."""
        for server in self.servers:
            if server.name == name:
                return server
        raise McpServerConfigurationError("MCP server name is not declared")
