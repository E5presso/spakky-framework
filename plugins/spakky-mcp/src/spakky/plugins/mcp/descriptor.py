"""Normalize external MCP tools into the agent tool catalog (issue #416).

ADR-0013 §2 keeps ``core/spakky-agent`` protocol-neutral and pushes the MCP
library dependency into this adapter plugin. A discovered MCP tool is turned
into an ``AgentToolDescriptor`` whose callable owns no instance parameter, so
``AgentToolDispatcher._with_owner_prefix`` invokes it without a bound target —
the owner-less path the framework runner already dispatches native
``@agent_tool`` methods through. External descriptors therefore reach the model
request and the dispatch loop on the identical catalog path.
"""

import copy
import dataclasses
from collections.abc import Awaitable, Callable, Sequence
from typing import cast, override

from mcp.types import CallToolResult, TextContent, Tool
from spakky.agent import (
    AgentRunner,
    AgentToolBoundInvocation,
    AgentToolCatalog,
    AgentToolDescriptor,
    AgentToolIdentity,
    AgentToolMetadata,
    AgentToolSchemaHandle,
    JsonObject,
    JsonValue,
    ToolApprovalRequirement,
    ToolEffects,
)
from spakky.agent.error import AgentDefinitionError

from spakky.plugins.mcp.constants import (
    MCP_EXTERNAL_TOOL_OWNER_MODULE,
    MCP_TOOL_NAME_SEPARATOR,
)
from spakky.plugins.mcp.error import (
    McpCatalogMergeError,
    McpResponseError,
    McpToolInvocationError,
)

# Callable bound to one external MCP tool. Its first parameter is VAR_KEYWORD,
# never self/cls, so the dispatcher invokes it without a bound target.
type McpToolCallable = Callable[..., Awaitable[JsonValue]]
# Builds a tool callable from a raw (unprefixed) MCP tool name; the live
# ``ClientSession`` is captured by the factory defined in ``client``.
type McpToolCallableFactory = Callable[[str], McpToolCallable]


class ExternalMcpTool:
    """Sentinel owner type for catalog descriptors discovered from MCP servers."""


class ExternalMcpToolDescriptor(AgentToolDescriptor):
    """Descriptor that binds the MCP argument object verbatim to its callable.

    The core binder (``bind_agent_tool_invocation``) reserves top-level ``args``
    and ``kwargs`` payload keys for its positional/keyword structured-call form.
    An external MCP tool may legitimately declare input fields named ``args`` or
    ``kwargs``; routing such a payload through that heuristic would fail to bind
    or drop the field name. MCP tool inputs are always a flat JSON object, so
    this descriptor forwards the whole payload as keyword arguments without the
    structured-call interpretation, preserving every declared field name.
    """

    @override
    def bind_invocation(self, payload: JsonObject) -> AgentToolBoundInvocation:
        """Forward the MCP argument object as keyword arguments verbatim."""
        return AgentToolBoundInvocation(args=(), kwargs=dict(payload))


def prefixed_tool_name(server_name: str, raw_tool_name: str) -> str:
    """Return the collision-safe model-facing name for an external tool."""
    return f"{server_name}{MCP_TOOL_NAME_SEPARATOR}{raw_tool_name}"


def build_external_descriptor(
    server_name: str,
    tool: Tool,
    callable_: McpToolCallable,
) -> AgentToolDescriptor:
    """Normalize one discovered MCP tool into a catalog descriptor."""
    name = prefixed_tool_name(server_name, tool.name)
    identity = AgentToolIdentity(
        owner_module=MCP_EXTERNAL_TOOL_OWNER_MODULE,
        owner_qualname=f"{ExternalMcpTool.__qualname__}.{server_name}",
        name=name,
    )
    output_schema = cast(JsonObject, tool.outputSchema) if tool.outputSchema else {}
    schema = AgentToolSchemaHandle(
        name=name,
        input_schema_name=f"{name}.input",
        output_schema_name=f"{name}.output",
        input_schema=_normalize_input_schema(tool.inputSchema),
        output_schema=output_schema,
    )
    return ExternalMcpToolDescriptor(
        identity=identity,
        owner=ExternalMcpTool,
        callable=callable_,
        schema=schema,
        description=tool.description,
        metadata=_external_tool_metadata(),
    )


def build_external_descriptors(
    server_name: str,
    tools: Sequence[Tool],
    callable_factory: McpToolCallableFactory,
) -> tuple[AgentToolDescriptor, ...]:
    """Normalize all discovered tools of one server into catalog descriptors."""
    return tuple(
        build_external_descriptor(server_name, tool, callable_factory(tool.name))
        for tool in tools
    )


def merge_external_catalog(
    native: AgentToolCatalog,
    external: Sequence[AgentToolDescriptor],
) -> AgentToolCatalog:
    """Return a catalog combining native descriptors with external MCP tools."""
    try:
        return AgentToolCatalog(descriptors=(*native.descriptors, *external))
    except AgentDefinitionError as e:
        raise McpCatalogMergeError from e


def build_mcp_runner(
    agent_instance: object,
    external: Sequence[AgentToolDescriptor],
) -> AgentRunner:
    """Build a runner whose catalog also carries external MCP tools.

    ``AgentRunner.for_agent_instance`` resolves the model and durable ports.
    The agent Pod metadata is a shared singleton, so its catalog is augmented on
    a ``copy.copy`` rather than in place; ``dataclasses.replace`` on the agent
    would reset the ``init=False`` ``tool_catalog`` to an empty default and drop
    the native tools, so the copy is required.
    """
    runner = AgentRunner.for_agent_instance(agent_instance)
    merged = merge_external_catalog(runner.agent.tool_catalog, external)
    augmented_agent = copy.copy(runner.agent)
    augmented_agent.tool_catalog = merged
    return dataclasses.replace(runner, agent=augmented_agent)


def normalize_call_result(result: CallToolResult) -> JsonValue:
    """Map an MCP tool result into a JSON value for evidence and the model."""
    if result.isError:
        raise McpToolInvocationError("MCP tool reported an error result")
    if result.structuredContent is not None:
        return cast(JsonValue, result.structuredContent)
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    if not texts:
        raise McpResponseError("MCP tool result carries no readable content")
    return {"content": texts}


def _normalize_input_schema(input_schema: object) -> JsonObject:
    if isinstance(input_schema, dict) and input_schema:
        return cast(JsonObject, input_schema)
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _external_tool_metadata() -> AgentToolMetadata:
    effects = ToolEffects.external_side_effect()
    return AgentToolMetadata(
        effects=effects,
        data_access=effects.data_access,
        externality=effects.externality,
        approval=ToolApprovalRequirement.DERIVED,
    )
