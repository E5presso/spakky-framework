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


class ModelToolChoice(StrEnum):
    """Provider-neutral tool calling strategy requested from a model adapter."""

    AUTO = "auto"
    NONE = "none"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class ModelToolSpec:
    """LLM-facing tool descriptor normalized by agent tooling."""

    name: str
    parameters: JsonSchemaConstraint
    description: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallingSpec:
    """Tool calling contract requested from a model adapter."""

    tools: Sequence[ModelToolSpec]
    choice: ModelToolChoice = ModelToolChoice.AUTO


@dataclass(frozen=True, slots=True)
class SamplingOptions:
    """Portable model sampling options."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StreamingOptions:
    """Portable model streaming options."""

    include_usage: bool = True
    include_progress: bool = True


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-neutral request passed to an agent model adapter."""

    messages: Sequence[ModelMessage]
    structured_output: StructuredOutputSpec | None = None
    tool_calling: ToolCallingSpec | None = None
    sampling: SamplingOptions = field(default_factory=SamplingOptions)
    streaming: StreamingOptions = field(default_factory=StreamingOptions)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Token accounting reported by a model adapter."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    """Tool invocation candidate emitted by a model adapter."""

    name: str
    arguments: JsonObject
    call_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelError:
    """Provider-neutral model failure payload."""

    code: str
    message: str
    retryable: bool = False
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Provider-neutral non-streaming model response."""

    content: str
    structured_output: JsonValue = None
    tool_calls: Sequence[ModelToolCall] = field(default_factory=tuple)
    usage: ModelUsage = field(default_factory=ModelUsage)
    metadata: JsonObject = field(default_factory=dict)


class ModelStreamEventKind(StrEnum):
    """Provider-neutral streaming event kinds emitted by a model adapter."""

    TOKEN_DELTA = "token_delta"
    TOOL_CALL_CANDIDATE = "tool_call_candidate"
    STRUCTURED_OUTPUT = "structured_output"
    PROGRESS = "progress"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class ModelStreamEvent:
    """Provider-neutral model streaming event."""

    kind: ModelStreamEventKind
    token_delta: str | None = None
    tool_call: ModelToolCall | None = None
    structured_output: JsonValue = None
    error: ModelError | None = None
    usage: ModelUsage | None = None
    metadata: JsonObject = field(default_factory=dict)


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
