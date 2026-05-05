"""Provider-neutral agent model port."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from spakky.agent.types import JsonObject, JsonValue


class ModelMessageRole(StrEnum):
    """Roles accepted by provider-neutral model messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    EVIDENCE = "evidence"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """Provider-neutral model message."""

    role: ModelMessageRole
    content: str
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JsonSchemaConstraint:
    """JSON schema constraint shared by structured output and tool calling."""

    schema: Mapping[str, JsonValue]
    strict: bool = True


@dataclass(frozen=True, slots=True)
class StructuredOutputSpec:
    """Structured output contract requested from a model adapter."""

    constraint: JsonSchemaConstraint
    output_type_name: str | None = None


@dataclass(frozen=True, slots=True)
class SamplingOptions:
    """Portable model sampling options."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-neutral request passed to an agent model adapter."""

    messages: Sequence[ModelMessage]
    structured_output: StructuredOutputSpec | None = None
    sampling: SamplingOptions = field(default_factory=SamplingOptions)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Token accounting reported by a model adapter."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Provider-neutral non-streaming model response."""

    content: str
    structured_output: JsonValue = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    metadata: JsonObject = field(default_factory=dict)


class ModelStreamEventKind(StrEnum):
    """Provider-neutral streaming event kinds emitted by a model adapter."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    PROGRESS = "progress"
    FINAL = "final"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ModelStreamEvent:
    """Provider-neutral model streaming event."""

    kind: ModelStreamEventKind
    text: str | None = None
    payload: JsonObject = field(default_factory=dict)
    usage: ModelUsage | None = None


class IAgentModel(ABC):
    """Outbound model adapter port owned by spakky-agent core."""

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a complete model response for the request."""
        ...

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Return provider-neutral stream events for the request."""
        ...
