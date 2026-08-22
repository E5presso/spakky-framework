"""Acceptance test: multi-turn sessions — persisted history + client-injected.

This is the SC-1 acceptance scenario for issue #411 (ADR-0013 §6). An @Agent
resolved and invoked through the Spakky application container continues a
conversation across turns by two paths:

- a server-persisted session keeps the prior user/assistant transcript in a
  TaskStore contribution and replays it on the next turn for the same
  conversation id (AG-UI threadId / A2A contextId);
- a stateless caller injects the prior transcript inline through
  RunAgentInput.message_history and no store is consulted.
"""

from collections.abc import AsyncIterator, Sequence
from typing import override

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentYield,
    ConversationTurn,
    IAgentModel,
    ITaskStore,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    RunAgentInput,
)
from spakky.agent.content import model_content_text
from spakky.agent.main import initialize


@Agent(spec=AgentExecutionSpec(name="conversational_assistant"))
class ConversationalAssistant:
    """Stateless assistant whose multi-turn memory is a TaskStore session."""

    def __init__(self, model: IAgentModel, task_store: ITaskStore) -> None:
        self._model = model
        self._task_store = task_store


async def test_persisted_session_continues_conversation_across_turns() -> None:
    """같은 conversation의 두 번째 턴이 컨테이너 경유로 이전 이력을 모델에 싣는다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(EchoingModel)
    app.add(MemoryTaskStore)
    app.add(ConversationalAssistant)
    app.start()

    assistant = app.container.get(ConversationalAssistant)
    model = app.container.get(IAgentModel)
    execute = vars(ConversationalAssistant)["execute"]

    await _drain(
        execute(
            assistant,
            RunAgentInput(
                state_id="turn-1",
                instruction="who was Einstein?",
                conversation_id="thread-42",
            ),
        )
    )
    await _drain(
        execute(
            assistant,
            RunAgentInput(
                state_id="turn-2",
                instruction="his famous equation?",
                conversation_id="thread-42",
            ),
        )
    )

    second_turn_request = _assert_recording(model).requests[1]
    assert _dialogue(second_turn_request) == [
        (ModelMessageRole.USER, "who was Einstein?"),
        (ModelMessageRole.ASSISTANT, "reply to: who was Einstein?"),
        (ModelMessageRole.USER, "his famous equation?"),
    ]
    app.stop()


async def test_client_injected_history_seeds_request_without_store() -> None:
    """클라이언트가 주입한 이력이 컨테이너 경유 단일 실행을 그대로 시드한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(EchoingModel)
    app.add(MemoryTaskStore)
    app.add(ConversationalAssistant)
    app.start()

    assistant = app.container.get(ConversationalAssistant)
    model = app.container.get(IAgentModel)
    execute = vars(ConversationalAssistant)["execute"]

    await _drain(
        execute(
            assistant,
            RunAgentInput(
                state_id="run-1",
                instruction="his famous equation?",
                conversation_id="thread-client",
                message_history=(
                    ModelMessage(ModelMessageRole.USER, "who was Einstein?"),
                    ModelMessage(ModelMessageRole.ASSISTANT, "a physicist"),
                ),
            ),
        )
    )

    store = app.container.get(ITaskStore)
    assert _dialogue(_assert_recording(model).requests[0]) == [
        (ModelMessageRole.USER, "who was Einstein?"),
        (ModelMessageRole.ASSISTANT, "a physicist"),
        (ModelMessageRole.USER, "his famous equation?"),
    ]
    # Client-owned transcript is never written back to the server session store.
    assert store.load_history("thread-client") == ()
    app.stop()


async def _drain(stream: AsyncIterator[AgentYield[object]]) -> None:
    async for _ in stream:
        ...


def _dialogue(request: ModelRequest) -> list[tuple[ModelMessageRole, str]]:
    return [
        (message.role, model_content_text(message.content))
        for message in request.messages
        if message.role is not ModelMessageRole.SYSTEM
    ]


def _assert_recording(model: IAgentModel) -> "EchoingModel":
    if not isinstance(model, EchoingModel):  # pragma: no cover - container wiring guard
        raise AssertionError("Expected the recording acceptance model")
    return model


@Pod()
class EchoingModel(IAgentModel):
    """Model that records requests and echoes the latest user instruction."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="recorded")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        latest = next(
            message.content
            for message in reversed(request.messages)
            if message.role is ModelMessageRole.USER
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.MESSAGE_DELTA,
            message_delta=f"reply to: {latest}",
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Pod()
class MemoryTaskStore(ITaskStore):
    """In-memory conversation-history store for the acceptance scenario."""

    def __init__(self) -> None:
        self._histories: dict[str, list[ConversationTurn]] = {}

    @override
    def load_history(self, conversation_id: str) -> tuple[ConversationTurn, ...]:
        return tuple(self._histories.get(conversation_id, ()))

    @override
    def append_turns(
        self,
        conversation_id: str,
        turns: Sequence[ConversationTurn],
    ) -> None:
        self._histories.setdefault(conversation_id, []).extend(turns)
