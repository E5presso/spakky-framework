"""Connection lifecycle and tool discovery for external MCP servers (issue #416).

An MCP ``ClientSession`` is only usable inside its transport context, so the
callables this module binds to descriptors close over a live session and stay
valid only while the connection is open. ``McpClient.open_runner`` keeps every
configured server's session open for the duration of the yielded runner, then
tears the connections down on exit.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from typing import override

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from httpx import AsyncClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.message import SessionMessage
from spakky.agent import (
    AgentRunner,
    AgentRunnerFactory,
    AgentToolDescriptor,
    IAgentRunnerFactory,
    JsonValue,
    RunAgentInput,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.mcp.auth import IMcpHttpClientProvider, McpHttpClientProvider
from spakky.plugins.mcp.config import McpConfig, McpServerConfig, McpTransport
from spakky.plugins.mcp.descriptor import (
    McpToolCallable,
    build_external_descriptors,
    build_mcp_runner,
    normalize_call_result,
)
from spakky.plugins.mcp.error import (
    McpToolDiscoveryError,
    McpToolInvocationError,
    McpTransportError,
)
from spakky.plugins.mcp.runtime import (
    IMcpRuntimeServerResolver,
    McpRuntimeServerResolver,
)

type McpReadStream = MemoryObjectReceiveStream[SessionMessage | Exception]
type McpWriteStream = MemoryObjectSendStream[SessionMessage]
# An open session paired with the descriptors discovered over it.
type DiscoveredServer = tuple[ClientSession, tuple[AgentToolDescriptor, ...]]


def make_mcp_tool_callable(
    session: ClientSession,
    raw_tool_name: str,
    call_timeout_seconds: float,
) -> McpToolCallable:
    """Bind an owner-less async callable that invokes one external MCP tool.

    The callable's only parameter is ``**arguments``: the dispatcher's
    owner-prefix step skips it (no leading self/cls) and binds the model payload
    straight to the keyword arguments forwarded to ``call_tool``. The configured
    per-server timeout bounds each call so a hung external tool cannot block the
    agent loop indefinitely.
    """
    read_timeout = timedelta(seconds=call_timeout_seconds)

    async def invoke(**arguments: object) -> JsonValue:
        try:
            result = await session.call_tool(
                raw_tool_name,
                arguments=dict(arguments),
                read_timeout_seconds=read_timeout,
            )
        except McpToolInvocationError:
            raise
        except Exception as e:  # MCP/transport failures surface as a typed error.
            raise McpToolInvocationError from e
        return normalize_call_result(result)

    return invoke


@asynccontextmanager
async def _transport_streams(
    server: McpServerConfig,
    http_client: AsyncClient | None = None,
) -> AsyncGenerator[tuple[McpReadStream, McpWriteStream], None]:
    """Yield the (read, write) stream pair for a server's transport."""
    if server.transport is McpTransport.STDIO:
        parameters = StdioServerParameters(
            command=server.command or "",
            args=list(server.args),
            env=dict(server.env) or None,
        )
        async with stdio_client(parameters) as (read, write):
            yield read, write
        return
    if http_client is None:
        async with streamable_http_client(server.url or "") as (
            read,
            write,
            _session_id,
        ):
            yield read, write
        return
    async with streamable_http_client(
        server.url or "",
        http_client=http_client,
    ) as (read, write, _session_id):
        yield read, write


@asynccontextmanager
async def connect_server(
    server: McpServerConfig,
    connect_timeout_seconds: float,
    http_client: AsyncClient | None = None,
) -> AsyncGenerator[DiscoveredServer, None]:
    """Open a server connection and discover its tools as catalog descriptors.

    ``connect_timeout_seconds`` bounds the ``initialize`` handshake (the session
    read timeout) so an unresponsive server fails fast instead of hanging the
    connection.
    """
    try:
        async with (
            _transport_streams(server, http_client) as (read, write),
            ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=connect_timeout_seconds),
            ) as session,
        ):
            await session.initialize()
            descriptors = await _discover_descriptors(session, server)
            yield session, descriptors
    except (McpToolDiscoveryError, McpToolInvocationError):
        raise
    except Exception as e:  # connection/initialize failures surface as transport.
        raise McpTransportError from e


async def _discover_descriptors(
    session: ClientSession,
    server: McpServerConfig,
) -> tuple[AgentToolDescriptor, ...]:
    try:
        listed = await session.list_tools()
    except Exception as e:
        raise McpToolDiscoveryError from e
    return build_external_descriptors(
        server.name,
        listed.tools,
        lambda raw_tool_name: make_mcp_tool_callable(
            session, raw_tool_name, server.call_timeout_seconds
        ),
    )


@Pod()
class McpClient(IAgentRunnerFactory):
    """Runner factory that joins external MCP tools to an agent runner."""

    def __init__(
        self,
        config: McpConfig,
        http_client_provider: IMcpHttpClientProvider | None = None,
        runtime_server_resolver: IMcpRuntimeServerResolver | None = None,
        runner_factory: AgentRunnerFactory | None = None,
    ) -> None:
        self.config = config
        self._runner_factory = runner_factory or AgentRunnerFactory()
        self._http_client_provider = http_client_provider or McpHttpClientProvider()
        self._runtime_server_resolver = (
            runtime_server_resolver or McpRuntimeServerResolver(config)
        )

    @asynccontextmanager
    @override
    async def open_runner(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> AsyncGenerator[AgentRunner, None]:
        """Yield a runner whose catalog also carries the external MCP tools."""
        descriptors: list[AgentToolDescriptor] = []
        servers = self._runtime_server_resolver.resolve_servers(
            agent_instance,
            run_input,
        )
        async with AsyncExitStack() as stack:
            for server in servers:
                http_client = await stack.enter_async_context(
                    self._http_client_provider.open_client(server)
                )
                _session, server_descriptors = await stack.enter_async_context(
                    connect_server(
                        server,
                        self.config.connect_timeout_seconds,
                        http_client,
                    )
                )
                descriptors.extend(server_descriptors)
            runner = await stack.enter_async_context(
                self._runner_factory.open_runner(agent_instance, run_input=run_input)
            )
            yield build_mcp_runner(runner, descriptors)
