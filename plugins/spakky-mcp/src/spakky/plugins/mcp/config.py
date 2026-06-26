"""Configuration for connecting external MCP servers to Spakky Agent runs."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.mcp.constants import (
    DEFAULT_MCP_CALL_TIMEOUT_SECONDS,
    DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS,
    MCP_TOOL_NAME_SEPARATOR,
    SPAKKY_MCP_CONFIG_ENV_PREFIX,
)
from spakky.plugins.mcp.error import McpServerConfigurationError


class McpTransport(StrEnum):
    """Transport an external MCP server is reached over."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class McpOAuthClientAuthMethod(StrEnum):
    """Client authentication method for OAuth2 client-credentials token requests."""

    CLIENT_SECRET_BASIC = "client_secret_basic"
    CLIENT_SECRET_POST = "client_secret_post"


class McpOAuthClientCredentialsConfig(BaseModel):
    """OAuth2 client-credentials declaration for an authenticated MCP server."""

    token_url: str
    client_id: str | None = None
    client_id_env: str | None = None
    client_secret: str | None = None
    client_secret_env: str | None = None
    scopes: tuple[str, ...] = ()
    audience: str | None = None
    extra_token_params: dict[str, str] = Field(default_factory=dict)
    client_auth_method: McpOAuthClientAuthMethod = (
        McpOAuthClientAuthMethod.CLIENT_SECRET_BASIC
    )

    @field_validator("token_url")
    @classmethod
    def _validate_token_url(cls, value: str) -> str:
        """Require a concrete HTTP(S) token endpoint."""
        if not _is_http_url(value):
            raise McpServerConfigurationError("MCP OAuth token url must be http(s)")
        return value

    @field_validator(
        "client_id",
        "client_id_env",
        "client_secret",
        "client_secret_env",
        "audience",
    )
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        """Reject blank optional auth values that would hide configuration errors."""
        if value is not None and not value.strip():
            raise McpServerConfigurationError("MCP OAuth auth value cannot be blank")
        return value

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank scopes before the token request is built."""
        if any(not item.strip() for item in value):
            raise McpServerConfigurationError("MCP OAuth scope cannot be blank")
        return value

    @model_validator(mode="after")
    def _validate_credential_sources(self) -> "McpOAuthClientCredentialsConfig":
        """Require one source each for client id and client secret."""
        if (self.client_id is None) == (self.client_id_env is None):
            raise McpServerConfigurationError(
                "MCP OAuth client credentials require exactly one client id source"
            )
        if (self.client_secret is None) == (self.client_secret_env is None):
            raise McpServerConfigurationError(
                "MCP OAuth client credentials require exactly one client secret source"
            )
        return self


class McpServerAuthConfig(BaseModel):
    """HTTP authentication declaration for a remote streamable_http MCP server."""

    headers: dict[str, str] = Field(default_factory=dict)
    bearer_token: str | None = None
    bearer_token_env: str | None = None
    oauth_client_credentials: McpOAuthClientCredentialsConfig | None = None

    @field_validator("headers")
    @classmethod
    def _validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject blank or multiline headers before building an HTTP client."""
        for name, item in value.items():
            if not name.strip() or not item.strip():
                raise McpServerConfigurationError(
                    "MCP HTTP auth headers cannot contain blank names or values"
                )
            if "\r" in name or "\n" in name or "\r" in item or "\n" in item:
                raise McpServerConfigurationError(
                    "MCP HTTP auth headers cannot contain newlines"
                )
        return value

    @field_validator("bearer_token", "bearer_token_env")
    @classmethod
    def _validate_bearer_text(cls, value: str | None) -> str | None:
        """Reject blank bearer token sources."""
        if value is not None and not value.strip():
            raise McpServerConfigurationError("MCP bearer token value cannot be blank")
        return value

    @model_validator(mode="after")
    def _validate_authorization_owner(self) -> "McpServerAuthConfig":
        """Ensure one feature owns the Authorization header."""
        if self.bearer_token is not None and self.bearer_token_env is not None:
            raise McpServerConfigurationError(
                "MCP bearer auth requires exactly one bearer token source"
            )
        uses_bearer = self.bearer_token is not None or self.bearer_token_env is not None
        if uses_bearer and self.oauth_client_credentials is not None:
            raise McpServerConfigurationError(
                "MCP auth cannot combine bearer token and OAuth token acquisition"
            )
        has_authorization_header = any(
            name.lower() == "authorization" for name in self.headers
        )
        if has_authorization_header and (
            uses_bearer or self.oauth_client_credentials is not None
        ):
            raise McpServerConfigurationError(
                "MCP auth cannot combine Authorization header with bearer/OAuth"
            )
        return self


class McpServerConfig(BaseModel):
    """Declaration of one external MCP server the agent consumes tools from."""

    name: str
    transport: McpTransport = McpTransport.STDIO
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    auth: McpServerAuthConfig = Field(default_factory=McpServerAuthConfig)
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
        if self.transport is McpTransport.STDIO and (
            self.auth.headers
            or self.auth.bearer_token is not None
            or self.auth.bearer_token_env is not None
            or self.auth.oauth_client_credentials is not None
        ):
            raise McpServerConfigurationError(
                "MCP server auth config applies only to streamable_http transport"
            )
        return self


def _is_http_url(url: str | None) -> bool:
    return url is not None and (url.startswith("http://") or url.startswith("https://"))


def validate_unique_server_names(
    servers: tuple[McpServerConfig, ...],
) -> tuple[McpServerConfig, ...]:
    """Reject duplicate MCP server names before runtime selection is ambiguous."""
    seen: set[str] = set()
    for server in servers:
        if server.name in seen:
            raise McpServerConfigurationError("MCP server names must be unique")
        seen.add(server.name)
    return servers


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

    def __init__(self) -> None:
        super().__init__()

    @model_validator(mode="after")
    def _validate_unique_servers(self) -> "McpConfig":
        """Require configured server names to be globally unique."""
        validate_unique_server_names(self.servers)
        return self

    def server_by_name(self, name: str) -> McpServerConfig:
        """Return the declared server with the given name."""
        for server in self.servers:
            if server.name == name:
                return server
        raise McpServerConfigurationError("MCP server name is not declared")
