# spakky-mcp

`spakky-mcp` is the Spakky Agent connector for external MCP servers.

It does one thing: connect MCP servers selected at run time and make their tools callable by the agent. It does not build MCP servers, and it does not expose an agent's own tools as an MCP server.

## When to use it

Use this plugin when an agent service needs to attach MCP servers supplied by the developer, the service, or the end user:

- a configured company MCP server,
- a tenant-specific remote MCP endpoint,
- a user-connected GitHub/Linear/search MCP server,
- a per-run inline MCP server declaration.

The MCP server itself can be implemented with FastMCP, the official MCP SDK, or any compatible server implementation.

## Install

```bash
uv add spakky-mcp
# or through the agent bundle
uv add "spakky[agent]"
```

Loading the plugin registers `McpClient` as `IAgentRunnerFactory`. Inbound adapters such as AG-UI and A2A can keep using the runner factory; MCP servers join the run through `RunAgentInput.metadata`.

## v7 breaking change

`spakky-mcp` v7 removes the reverse "Agent tools as an MCP server" surface:

- removed `MCPServer`, `MCPToolServer`, `McpToolServerConfig`,
  `build_agent_tool_server`, `serve_stdio`, and the server registry modules,
- removed `McpConfig.tool_server`,
- removed Agent annotations whose only purpose was exposing local Agent tools
  as an MCP server.

The replacement path is intentionally one-way:

1. Build MCP servers with FastMCP, the official MCP SDK, or another MCP server
   framework.
2. Register allowed servers in `McpConfig.servers` or accept per-run inline
   declarations from user/service settings.
3. Pass selected servers through `RunAgentInput.metadata["mcp"]["servers"]`.
4. Let `spakky-mcp` attach those external tools lazily through
   `mcp_search_tools` and `mcp_call_tool`.

## Configure servers

Configured servers use the `SPAKKY_MCP__` settings prefix.

```bash
export SPAKKY_MCP__SERVERS='[
  {"name": "weather", "transport": "stdio", "command": "weather-mcp-server"}
]'
```

| Setting | Meaning | Default |
|---------|---------|---------|
| `SPAKKY_MCP__SERVERS` | JSON array of external MCP server declarations | `[]` |
| `SPAKKY_MCP__CONNECT_TIMEOUT_SECONDS` | MCP connection timeout in seconds | `30.0` |

Server fields:

| Field | Meaning |
|-------|---------|
| `name` | Unique server name for one run. It cannot contain `__`. |
| `transport` | `stdio` or `streamable_http` |
| `command`, `args`, `env` | stdio server process command, arguments, and environment |
| `url` | streamable HTTP MCP endpoint |
| `auth.headers` | Static HTTP headers |
| `auth.bearer_token_env` | Environment variable containing a bearer token |
| `auth.oauth_client_credentials` | OAuth2 client-credentials token request config |
| `call_timeout_seconds` | Per-tool call timeout. Default `60.0` |

## Runtime selection

At run time, pass configured server names or inline declarations through `RunAgentInput.metadata["mcp"]["servers"]`.

```python
from spakky.agent import IAgentRunnerFactory, RunAgentInput


async def run_with_user_mcp(factory: IAgentRunnerFactory, agent: object) -> None:
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer with external tools",
        metadata={"mcp": {"servers": ["weather"]}},
    )
    async with factory.open_runner(agent, run_input=run_input) as runner:
        async for item in runner.run(run_input):
            ...
```

Inline server declarations support user self-service connections:

```python
RunAgentInput(
    state_id="run-2",
    instruction="inspect issue status",
    metadata={
        "mcp": {
            "servers": [
                {
                    "name": "tenant-linear",
                    "transport": "streamable_http",
                    "url": "https://tenant.example.com/mcp",
                    "auth": {"bearer_token": access_token},
                }
            ]
        }
    },
)
```

Production services usually implement `IMcpRuntimeServerResolver` so a request carries stable connection IDs, while the server loads URLs and credentials from a DB or vault. Register that resolver as a Pod and bind it over the default resolver:

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.plugin import Plugin
from spakky.plugins.mcp import IMcpRuntimeServerResolver


PLUGIN_NAME = Plugin(name="my-mcp-connections")


def initialize(app: SpakkyApplication) -> None:
    app.add(UserMcpResolver)
    app.container.bind_to_type(IMcpRuntimeServerResolver, UserMcpResolver)
```

Browser users should generally be allowed to add `streamable_http` endpoints, not arbitrary `stdio` commands.

AG-UI maps `forwardedProps.mcp` into the same metadata shape. A2A maps the data part `mcp` object into the same shape.

## Lazy tool search

MCP servers can expose many tools. `spakky-mcp` does not push every external tool schema into the initial model request. The model sees only two MCP meta-tools:

| Tool | Purpose |
|------|---------|
| `mcp_search_tools` | Search tools available from the MCP servers attached to this run. |
| `mcp_call_tool` | Call one tool returned by `mcp_search_tools`. |

External tool names are returned by search as `<server_name>__<tool_name>`. For example, `weather` server tool `forecast` becomes `weather__forecast`.

This keeps large MCP toolsets from polluting the model context while still letting the model discover and invoke the tools it needs.
When `mcp_call_tool` requires human approval, the approval request names the selected external MCP tool and includes the selected arguments in metadata.

## Development checks

Run package checks from this package directory:

```bash
uv run ruff format .
uv run ruff check .
uv run --project ../.. pyrefly check --disable-project-excludes-heuristics --min-severity warn --no-progress-bar --output-format min-text
uv run pytest
```

## License

MIT License
