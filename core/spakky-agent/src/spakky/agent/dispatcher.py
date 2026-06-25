"""Declarative tool dispatch over a discovered agent tool catalog.

ADR-0013 §1 hands the model-call -> tool-invoke step to the framework runner.
This module removes the developer-written ``if call.name == ...`` chain and the
manual payload extraction it implied: a model tool call is resolved against the
catalog, its arguments are bound through the descriptor, and the descriptor's
callable is invoked. External MCP tools (follow-up F1) normalize into the same
``AgentToolCatalog`` and therefore dispatch through this identical path.
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from inspect import iscoroutinefunction, signature

from spakky.agent.error import AgentToolDispatchError
from spakky.agent.interfaces.model import ModelToolCall
from spakky.agent.tooling import (
    AgentToolCallable,
    AgentToolCatalog,
    AgentToolDescriptor,
)

_OWNER_PARAMETER_NAMES = ("self", "cls")


@dataclass(frozen=True, slots=True)
class AgentToolDispatcher:
    """Resolve and invoke a catalog tool from a model tool call.

    The dispatcher binds to a single agent instance whose ``@agent_tool``
    methods are described by ``catalog``. Catalog descriptors that own no
    instance parameter (such as MCP-normalized external tools) are invoked
    without the bound ``target``.
    """

    # target: any agent instance owning the catalog tools — no common base type.
    target: object
    catalog: AgentToolCatalog

    def descriptor_for(self, call: ModelToolCall) -> AgentToolDescriptor:
        """Resolve the catalog descriptor a model tool call targets."""
        for descriptor in self.catalog.descriptors:
            if descriptor.schema.name == call.name:
                return descriptor
        raise AgentToolDispatchError("Agent tool call names an unregistered tool")

    # Returns object: tool results are heterogeneous per tool — the adapter
    # owns serialization of the concrete return value into evidence/yield.
    async def dispatch(self, call: ModelToolCall) -> object:
        """Bind a model tool call payload and invoke its catalog callable."""
        descriptor = self.descriptor_for(call)
        invocation = descriptor.bind_invocation(call.arguments)
        callable_ = descriptor.callable
        positional = self._with_owner_prefix(callable_, invocation.args)
        if iscoroutinefunction(callable_):
            awaitable: Awaitable[object] = callable_(
                *positional,
                **invocation.kwargs,
            )
            return await awaitable
        return callable_(*positional, **invocation.kwargs)

    def _with_owner_prefix(
        self,
        callable_: AgentToolCallable,
        args: tuple[object, ...],
    ) -> tuple[object, ...]:
        parameters = tuple(signature(callable_).parameters.values())
        if parameters and parameters[0].name in _OWNER_PARAMETER_NAMES:
            return (self.target, *args)
        return args
