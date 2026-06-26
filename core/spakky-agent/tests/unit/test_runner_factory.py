"""Tests for request-scoped Agent runner assembly."""

from collections.abc import AsyncIterator
from typing import override

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunnerFactory,
    IAgentModel,
    IAgentModelResolver,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    RunAgentInput,
)


class _Model(IAgentModel):
    """Small model double identified by name."""

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content=self.name)

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        return _empty_stream()


class _Resolver(IAgentModelResolver):
    """Resolver returning a run-specific model for one selector."""

    def __init__(self, selected: IAgentModel | None) -> None:
        self.selected = selected
        self.last_input: RunAgentInput | None = None

    @override
    def resolve_model(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> IAgentModel | None:
        self.last_input = run_input
        return self.selected


@Agent(spec=AgentExecutionSpec(name="model_switchable"))
class _ModelSwitchableAgent:
    """Agent fixture with a fallback constructor-injected model."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


async def test_runner_factory_uses_resolver_model_for_one_run() -> None:
    """Runner factory can replace the constructor model for a specific run."""
    fallback = _Model("fallback")
    selected = _Model("openrouter")
    resolver = _Resolver(selected)
    factory = AgentRunnerFactory(model_resolver=resolver)
    run_input = RunAgentInput(
        state_id="run-1",
        instruction="answer",
        metadata={"model": {"provider": "openrouter", "name": "anthropic/claude"}},
    )

    async with factory.open_runner(
        _ModelSwitchableAgent(fallback),
        run_input=run_input,
    ) as runner:
        assert runner.model is selected

    assert resolver.last_input is run_input


async def test_runner_factory_keeps_injected_model_when_resolver_returns_none() -> None:
    """A resolver can decline a run and leave the injected fallback model in place."""
    fallback = _Model("fallback")
    factory = AgentRunnerFactory(model_resolver=_Resolver(None))

    async with factory.open_runner(
        _ModelSwitchableAgent(fallback),
        run_input=RunAgentInput(state_id="run-2", instruction="answer"),
    ) as runner:
        assert runner.model is fallback


async def _empty_stream() -> AsyncIterator[ModelStreamEvent]:
    if False:
        yield ModelStreamEvent()
