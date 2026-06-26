"""Provider-neutral agent model port."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import cast

from spakky.agent.context import ContextDigest, ContextManifest, ContextPack
from spakky.agent.error import AgentDefinitionError
from spakky.agent.safety import (
    ContextExposurePolicy,
    EvidenceExposurePolicy,
    SensitiveFieldDescriptor,
    guard_json_value,
)
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
class ModelSelection:
    """Provider/model selector carried by one Agent run.

    A service may let a user choose OpenAI, Anthropic, Vertex, OpenRouter, vLLM,
    or another provider per run. The selector is intentionally provider-neutral:
    concrete adapters or routing models decide which values they accept.
    """

    provider: str | None = None
    model: str | None = None
    profile: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject blank selector fields before they reach provider adapters."""
        for label, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("profile", self.profile),
        ):
            if value is not None and not value.strip():
                raise AgentDefinitionError(f"Model selection {label} cannot be blank")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-neutral request passed to an agent model adapter."""

    messages: Sequence[ModelMessage]
    context: Sequence[ContextPack] = field(default_factory=tuple)
    context_manifest: ContextManifest | None = None
    context_digest: ContextDigest | None = None
    structured_output: StructuredOutputSpec | None = None
    tool_calling: ToolCallingSpec | None = None
    sampling: SamplingOptions = field(default_factory=SamplingOptions)
    streaming: StreamingOptions = field(default_factory=StreamingOptions)
    model_selection: ModelSelection | None = None
    metadata: JsonObject = field(default_factory=dict)

    def assemble_messages(
        self,
        policy: ContextExposurePolicy | None = None,
    ) -> tuple[ModelMessage, ...]:
        """Assemble prompt messages from typed context packs without concatenation."""
        exposure_policy = policy or ContextExposurePolicy()
        context_messages = tuple(
            ModelMessage(
                role=ModelMessageRole.EVIDENCE,
                content=pack.guarded_content(exposure_policy),
                metadata=pack.message_metadata(exposure_policy),
            )
            for pack in self.context
        )
        return (*self.messages, *context_messages)


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

    def guarded(
        self,
        sensitive_fields: Sequence[SensitiveFieldDescriptor],
        policy: EvidenceExposurePolicy | None = None,
    ) -> "ModelToolCall":
        """Return a copy with sensitive argument values deterministically guarded."""
        exposure_policy = policy or EvidenceExposurePolicy()
        guarded_arguments = guard_json_value(
            self.arguments,
            sensitive_fields,
            exposure_policy,
        )
        if not isinstance(guarded_arguments, Mapping):
            guarded_arguments = {}
        return replace(self, arguments=guarded_arguments)


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

    def guarded(
        self,
        sensitive_fields: Sequence[SensitiveFieldDescriptor],
        policy: EvidenceExposurePolicy | None = None,
    ) -> "ModelResponse":
        """Return a copy with sensitive output payloads deterministically guarded."""
        exposure_policy = policy or EvidenceExposurePolicy()
        content = self.content
        structured_output = self.structured_output
        content_descriptors = tuple(
            descriptor
            for descriptor in sensitive_fields
            if descriptor.path in ((), ("content",))
        )
        if content_descriptors:
            guarded_content = guard_json_value(
                {"content": content},
                tuple(
                    SensitiveFieldDescriptor(("content",), descriptor.field)
                    for descriptor in content_descriptors
                ),
                exposure_policy,
            )
            content_value = cast(Mapping[str, JsonValue], guarded_content).get(
                "content"
            )
            if isinstance(content_value, str):
                content = content_value
            else:
                content = "[REDACTED]"
        structured_output_descriptors = tuple(
            descriptor
            for descriptor in sensitive_fields
            if descriptor.path not in ((), ("content",))
        )
        if structured_output_descriptors:
            structured_output = guard_json_value(
                structured_output,
                structured_output_descriptors,
                exposure_policy,
            )
        return replace(self, content=content, structured_output=structured_output)


class ModelStreamEventKind(StrEnum):
    """Provider-neutral streaming event kinds emitted by a model adapter."""

    TOKEN_DELTA = "token_delta"
    MESSAGE_DELTA = "message_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS_DELTA = "tool_call_args_delta"
    TOOL_CALL_END = "tool_call_end"
    TOOL_CALL_CANDIDATE = "tool_call_candidate"
    STRUCTURED_OUTPUT = "structured_output"
    PROGRESS = "progress"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class ModelStreamEvent:
    """Provider-neutral model streaming event.

    ``token_delta`` carries the generic streamed token channel. ``message_delta``
    and ``reasoning_delta`` distinguish assistant-facing text from model reasoning
    so callers can route or suppress reasoning independently. ``tool_call_args_delta``
    carries incremental tool-call argument text framed by ``TOOL_CALL_START`` and
    ``TOOL_CALL_END`` boundary events that reference the same ``tool_call``.
    """

    kind: ModelStreamEventKind
    token_delta: str | None = None
    message_delta: str | None = None
    reasoning_delta: str | None = None
    tool_call: ModelToolCall | None = None
    tool_call_args_delta: str | None = None
    structured_output: JsonValue = None
    error: ModelError | None = None
    usage: ModelUsage | None = None
    metadata: JsonObject = field(default_factory=dict)

    @staticmethod
    def _guard_text_delta(
        field_name: str,
        value: str,
        sensitive_fields: Sequence[SensitiveFieldDescriptor],
        policy: EvidenceExposurePolicy,
    ) -> str:
        """Guard one streamed text channel against root or path-bound descriptors."""
        descriptors = tuple(
            descriptor
            for descriptor in sensitive_fields
            if descriptor.path in ((), (field_name,))
        )
        if not descriptors:
            return value
        guarded = guard_json_value(
            {field_name: value},
            tuple(
                SensitiveFieldDescriptor((field_name,), descriptor.field)
                for descriptor in descriptors
            ),
            policy,
        )
        guarded_value = cast(Mapping[str, JsonValue], guarded).get(field_name)
        return guarded_value if isinstance(guarded_value, str) else "[REDACTED]"

    def guarded(
        self,
        sensitive_fields: Sequence[SensitiveFieldDescriptor],
        policy: EvidenceExposurePolicy | None = None,
    ) -> "ModelStreamEvent":
        """Return a copy with sensitive streaming payloads guarded."""
        exposure_policy = policy or EvidenceExposurePolicy()
        text_channels: dict[str, str | None] = {
            "token_delta": self.token_delta,
            "message_delta": self.message_delta,
            "reasoning_delta": self.reasoning_delta,
            "tool_call_args_delta": self.tool_call_args_delta,
        }
        guarded_text = {
            field_name: self._guard_text_delta(
                field_name, value, sensitive_fields, exposure_policy
            )
            for field_name, value in text_channels.items()
            if value is not None
        }
        text_paths = (
            (),
            *((field_name,) for field_name in text_channels),
        )
        structured_output = self.structured_output
        structured_descriptors = tuple(
            descriptor
            for descriptor in sensitive_fields
            if descriptor.path not in text_paths
        )
        if structured_descriptors:
            structured_output = guard_json_value(
                structured_output,
                structured_descriptors,
                exposure_policy,
            )
        tool_call = self.tool_call
        if tool_call is not None:
            tool_call = tool_call.guarded(sensitive_fields, exposure_policy)
        return replace(
            self,
            structured_output=structured_output,
            tool_call=tool_call,
            **guarded_text,
        )


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Provider-neutral declaration of a model backend's queryable abilities.

    The agent runner consults this descriptor before a run to adjust behaviour
    without invoking the backend. ``supports_reasoning`` gates whether the runner
    expects ``REASONING_DELTA`` events; when False the adapter omits them rather
    than failing (graceful degrade). ``context_window_tokens`` is ``None`` when the
    backend does not declare a fixed limit. ``supports_token_counting`` declares
    whether the backend can report token accounting for a request before sending it.
    """

    supports_reasoning: bool = False
    context_window_tokens: int | None = None
    supports_token_counting: bool = False


class IAgentModel(ABC):
    """Outbound model adapter port owned by spakky-agent core."""

    @property
    @abstractmethod
    def capability(self) -> ModelCapability:
        """Return the backend capability descriptor queryable before a run."""
        ...

    def capability_for(
        self,
        selection: ModelSelection | None = None,
    ) -> ModelCapability:
        """Return capability for a run-specific model selection.

        Existing fixed-model adapters can ignore the selector and inherit the
        default. Routing adapters can override this to expose per-model context
        windows, reasoning support, or token-counting support before a request.
        """
        _ = selection
        return self.capability

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a complete model response for the request."""
        ...

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Return provider-neutral stream events for the request."""
        ...
