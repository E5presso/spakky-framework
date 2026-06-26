"""DI entry point for opening agent runners.

Protocol adapters should not construct :class:`AgentRunner` directly when an
application may load runner-augmenting plugins such as MCP.  They ask this
factory port for a runner scoped to one request instead; plugins can then bind
the port to their own implementation while the default remains the native
framework runner.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import override

from spakky.core.pod.annotations.pod import Pod

from spakky.agent.runner import AgentRunner


class IAgentRunnerFactory(ABC):
    """Port for opening a request-scoped runner for one agent instance."""

    @abstractmethod
    def open_runner(
        self,
        agent_instance: object,
        server_names: Sequence[str] | None = None,
    ) -> AbstractAsyncContextManager[AgentRunner]:
        """Yield a runner bound to ``agent_instance`` for one adapter request."""
        ...


@Pod()
class AgentRunnerFactory(IAgentRunnerFactory):
    """Default runner factory using the native framework-owned runner."""

    @override
    @asynccontextmanager
    async def open_runner(
        self,
        agent_instance: object,
        server_names: Sequence[str] | None = None,
    ) -> AsyncGenerator[AgentRunner, None]:
        """Yield the native runner; ``server_names`` is for plugin overrides."""
        _ = server_names
        yield AgentRunner.for_agent_instance(agent_instance)
