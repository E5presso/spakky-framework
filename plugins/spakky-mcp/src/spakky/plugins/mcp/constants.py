"""Constants for the spakky-mcp external server adapter."""

SPAKKY_MCP_CONFIG_ENV_PREFIX: str = "SPAKKY_MCP__"
DEFAULT_MCP_CONNECT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_MCP_CALL_TIMEOUT_SECONDS: float = 60.0

# External MCP tools own no class; descriptors derive their identity module from
# this plugin so catalog keys stay stable and disjoint from native @agent_tool keys.
MCP_EXTERNAL_TOOL_OWNER_MODULE: str = "spakky.plugins.mcp"

# Separates a server name from a raw tool name in the model-facing tool name. A
# double underscore avoids the dotted form some model tool-name validators reject.
MCP_TOOL_NAME_SEPARATOR: str = "__"
