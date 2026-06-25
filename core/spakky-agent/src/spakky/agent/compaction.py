"""Pluggable context-compaction strategies (ADR-0013 §7).

A long conversation eventually outgrows a model backend's context window. The
framework runner owns when to compact (ADR-0013 §1 declarative loop ownership);
this module owns *how*. ``ICompactionStrategy`` is the provider-neutral port a
developer declares in an ``@Agent`` spec, and the runner applies the declared
chain to the resolved history before each model request once the running token
estimate crosses the policy threshold.

The port shape follows pydantic-ai's message-history processor / ``ProcessHistory``
capability: a processor receives the message list (plus run context such as token
usage) and returns a transformed list. Here the contextual inputs are made
explicit parameters — the running ``ModelUsage`` and the backend ``ModelCapability``
— so a strategy decides how aggressively to compact from the same signals the
runner uses to decide *whether* to compact. Strategies are pure transforms over
``tuple[ModelMessage, ...]`` and compose by sequential application, so a chain of
strategies is just each applied to the previous one's output.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import (
    IAgentModel,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelUsage,
)

SUMMARY_MESSAGE_METADATA_KEY = "compaction"
"""Metadata flag marking a message the summarize strategy synthesized."""

SUMMARY_MESSAGE_METADATA_VALUE = "summary"
"""Metadata value identifying a synthesized transcript summary message."""

DEFAULT_SUMMARY_INSTRUCTION = (
    "Summarize the earlier conversation turns below into a concise briefing that "
    "preserves decisions, facts, and open questions. Reply with the summary only."
)
"""Fallback instruction for the secondary model that summarizes old turns."""


class ICompactionStrategy(ABC):
    """Provider-neutral context-compaction transform applied before a request.

    A strategy maps a resolved history to a shorter one, reading the running
    ``ModelUsage`` and backend ``ModelCapability`` so it can scale its effect to
    how close the run is to the context limit. Implementations are pure transforms
    — they never mutate the input — so the runner can apply a declared chain by
    threading each strategy's output into the next.
    """

    @abstractmethod
    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        """Return a compacted view of ``history`` for the next model request."""
        ...


@dataclass(frozen=True, slots=True)
class KeepRecentMessagesCompactionStrategy(ICompactionStrategy):
    """Sliding-window strategy that keeps only the most recent messages.

    The cheapest compaction: drop the oldest messages and keep the last
    ``max_messages``. It carries no model dependency, so it is the safe default
    tail of a chain that bounds history length regardless of content.
    """

    max_messages: int

    def __post_init__(self) -> None:
        """Reject a window that would keep no messages."""
        if self.max_messages <= 0:
            raise AgentDefinitionError(
                "Keep-recent compaction window must keep at least one message"
            )

    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        """Keep only the last ``max_messages`` messages of the history."""
        return history[-self.max_messages :]


@dataclass(frozen=True, slots=True)
class TrimToolResultsCompactionStrategy(ICompactionStrategy):
    """Truncate verbose tool-result messages while preserving the dialogue.

    Tool results (search dumps, file contents) dominate token cost yet rarely
    need to be replayed verbatim. This strategy truncates only ``TOOL`` role
    message content past ``max_characters`` and leaves the user/assistant turns
    untouched, so the model still sees that a tool ran and a clipped head of its
    output.
    """

    max_characters: int

    def __post_init__(self) -> None:
        """Reject a non-positive truncation budget."""
        if self.max_characters <= 0:
            raise AgentDefinitionError(
                "Tool-result trim budget must be a positive character count"
            )

    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        """Truncate over-budget tool-result content, leaving other roles intact."""
        return tuple(self._trim(message) for message in history)

    def _trim(self, message: ModelMessage) -> ModelMessage:
        if message.role is not ModelMessageRole.TOOL:
            return message
        if len(message.content) <= self.max_characters:
            return message
        return ModelMessage(
            role=message.role,
            content=message.content[: self.max_characters],
            metadata=message.metadata,
        )


@dataclass(frozen=True, slots=True)
class ProviderManagedCompactionStrategy(ICompactionStrategy):
    """No-op strategy for backends that manage their own context window.

    Some providers compact server-side, so the framework must not also trim the
    transcript. Declaring this strategy makes that hand-off explicit in the spec
    rather than leaving compaction silently absent.
    """

    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        """Return the history unchanged — the provider owns compaction."""
        return history


@dataclass(frozen=True, slots=True)
class SummarizeOldTurnsCompactionStrategy(ICompactionStrategy):
    """Replace older turns with a model-generated summary, keeping recent ones.

    The richest compaction: a secondary model call condenses the turns older than
    ``keep_recent`` into one ``EVIDENCE`` summary message that precedes the kept
    tail. This preserves earlier context as a briefing instead of dropping it, at
    the cost of one extra model round-trip. When the history is already within
    ``keep_recent`` there is nothing older to summarize, so the call is skipped.
    """

    model: IAgentModel
    keep_recent: int
    summary_instruction: str = DEFAULT_SUMMARY_INSTRUCTION

    def __post_init__(self) -> None:
        """Reject a window that would leave no recent turns to anchor the summary."""
        if self.keep_recent <= 0:
            raise AgentDefinitionError(
                "Summarize compaction must keep at least one recent message"
            )
        if not self.summary_instruction.strip():
            raise AgentDefinitionError(
                "Summarize compaction instruction cannot be blank"
            )

    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        """Summarize turns older than ``keep_recent`` ahead of the recent tail."""
        if len(history) <= self.keep_recent:
            return history
        older = history[: len(history) - self.keep_recent]
        recent = history[len(history) - self.keep_recent :]
        summary = await self.model.complete(self._summary_request(older))
        return (self._summary_message(summary.content), *recent)

    def _summary_request(self, older: tuple[ModelMessage, ...]) -> ModelRequest:
        transcript = "\n".join(
            f"{message.role.value}: {message.content}" for message in older
        )
        return ModelRequest(
            messages=(
                ModelMessage(ModelMessageRole.SYSTEM, self.summary_instruction),
                ModelMessage(ModelMessageRole.USER, transcript),
            )
        )

    @staticmethod
    def _summary_message(content: str) -> ModelMessage:
        return ModelMessage(
            role=ModelMessageRole.EVIDENCE,
            content=content,
            metadata={SUMMARY_MESSAGE_METADATA_KEY: SUMMARY_MESSAGE_METADATA_VALUE},
        )
