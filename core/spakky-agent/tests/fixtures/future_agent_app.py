"""Scannable Agent fixture using postponed annotations."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from spakky.agent import Agent, AgentYield, AgentYieldKind, Final


@Agent()
class FutureAnnotatedAgent:
    """Agent fixture whose execute return annotation is stored as a string."""

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Yield a final item after postponed annotations are resolved."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )
