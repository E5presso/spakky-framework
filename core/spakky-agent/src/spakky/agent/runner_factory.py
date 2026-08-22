"""DI entry point for opening agent runners.

Protocol adapters should not construct :class:`AgentRunner` directly when an
application may load runner-augmenting plugins such as MCP.  They ask this
factory port for a runner scoped to one request instead; plugins can then bind
the port to their own implementation while the default remains the native
framework runner.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import override

from spakky.core.pod.annotations.pod import Pod

from spakky.agent.cost import ModelPricingCatalog
from spakky.agent.inbound import RunAgentInput
from spakky.agent.model_resolver import IAgentModelResolver
from spakky.agent.runner import AgentRunner
from spakky.agent.telemetry import IAgentTelemetry


class IAgentRunnerFactory(ABC):
    """Port for opening a request-scoped runner for one agent instance."""

    @abstractmethod
    def open_runner(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> AbstractAsyncContextManager[AgentRunner]:
        """Yield a runner bound to ``agent_instance`` for one adapter request."""
        ...


@Pod()
class AgentRunnerFactory(IAgentRunnerFactory):
    """Default runner factory using the native framework-owned runner."""

    def __init__(
        self,
        model_resolver: IAgentModelResolver | None = None,
        telemetry: IAgentTelemetry | None = None,
        pricing: ModelPricingCatalog | None = None,
    ) -> None:
        self._model_resolver = model_resolver
        self._telemetry = telemetry
        self._pricing = pricing

    @override
    @asynccontextmanager
    async def open_runner(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> AsyncGenerator[AgentRunner, None]:
        """Yield the native runner for one request."""
        runner = AgentRunner.for_agent_instance(agent_instance)
        if self._model_resolver is not None:
            model = self._model_resolver.resolve_model(agent_instance, run_input)
            if model is not None:
                runner = runner.with_model(model)
        if self._telemetry is not None:
            runner = runner.with_telemetry(self._telemetry)
        if self._pricing is not None:
            runner = runner.with_pricing(self._pricing)
        yield runner
