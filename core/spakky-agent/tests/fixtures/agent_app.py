"""Scannable application module containing an Agent Pod."""

from collections.abc import AsyncGenerator

from spakky.core.pod.annotations.pod import Pod

from spakky.agent import Agent, AgentExecutionSpec, AgentYield, AgentYieldKind, Final


@Pod()
class AnswerTools:
    """Simple constructor dependency resolved through the Spakky container."""

    def answer(self, command: str) -> str:
        """Return a deterministic answer for direct invocation tests."""
        return f"handled:{command}"


@Agent(spec=AgentExecutionSpec(name="code_assistant", objective="handle commands"))
class CodeAssistant:
    """Agent fixture shaped like a UseCase with constructor DI."""

    def __init__(self, tools: AnswerTools) -> None:
        """Receive outbound capability through constructor DI."""
        self._tools = tools

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Yield a final item so inbound adapters can consume the stream directly."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=self._tools.answer(command), metadata={}),
        )
