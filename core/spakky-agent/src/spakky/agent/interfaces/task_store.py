"""Persistence port for multi-turn conversation history (ADR-0013 §6).

ADR-0013 §6 supports multi-turn conversations through two paths that the
framework runner reconciles:

- **server-side persisted sessions** — the framework persists the running
  transcript and continues it by ``conversation_id``. This port is that
  conversation-history persistence contract. It is protocol-neutral, but it is
  not the A2A task snapshot repository: ``spakky-a2a`` owns A2A ``Task`` storage
  through its plugin repository and bridges it to ``a2a-sdk`` ``TaskStore``.
- **client-injected history** — a stateless caller passes the prior transcript
  on each run (``RunAgentInput.message_history``) and no store is consulted.

The ``conversation_id`` key is the protocol-neutral thread identifier carried by
every event (``AgentEventAttribution.conversation_id``) and seeded by
``RunAgentInput.effective_conversation_id``. AG-UI projects it as ``threadId``
and A2A projects it as ``contextId`` when an adapter wants transcript replay;
A2A protocol ``Task`` records remain plugin-owned snapshots.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import ModelMessage, ModelMessageRole
from spakky.agent.types import JsonObject


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """One persisted exchange in a multi-turn conversation transcript.

    A turn is the protocol-neutral unit a ``TaskStore`` persists: who spoke
    (``role``) and what was said (``content``). It is intentionally narrower than
    a model-request ``ModelMessage`` — the transcript records the user/assistant
    dialogue that seeds future turns, not the system or evidence framing the
    runner assembles fresh on each request. ``as_model_message`` projects a turn
    back into the model-request vocabulary when the runner replays history.
    """

    role: ModelMessageRole
    content: str
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject turns that cannot seed a future model request."""
        if self.role not in (ModelMessageRole.USER, ModelMessageRole.ASSISTANT):
            raise AgentDefinitionError(
                "Conversation turn role must be user or assistant"
            )
        if not self.content.strip():
            raise AgentDefinitionError("Conversation turn content cannot be blank")

    def as_model_message(self) -> ModelMessage:
        """Project this turn into a model-request message for history replay."""
        return ModelMessage(
            role=self.role, content=self.content, metadata=self.metadata
        )


class ITaskStore(ABC):
    """Durable conversation-history store keyed by ``conversation_id``.

    Persists the running transcript of a server-side session so a later run with
    the same ``conversation_id`` continues the conversation (ADR-0013 §6). A2A
    can map its ``contextId`` to this key for transcript replay, while A2A task
    snapshots are stored by ``spakky-a2a``'s repository bridge.
    """

    @abstractmethod
    def load_history(self, conversation_id: str) -> Sequence[ConversationTurn]:
        """Return the persisted transcript for a conversation in turn order.

        Returns an empty sequence for a conversation that has no persisted turns
        yet — the first turn of a brand-new conversation.
        """
        ...

    @abstractmethod
    def append_turns(
        self,
        conversation_id: str,
        turns: Sequence[ConversationTurn],
    ) -> None:
        """Append new turns to a conversation's transcript in order."""
        ...
