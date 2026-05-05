"""Provider-neutral agent model port."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import cast

from spakky.agent.context import ContextDigest, ContextManifest, ContextPack
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

    def guarded(
        self,
        sensitive_fields: Sequence[SensitiveFieldDescriptor],
        policy: EvidenceExposurePolicy | None = None,
    ) -> "ModelStreamEvent":
        """Return a copy with sensitive streaming payloads guarded."""
        exposure_policy = policy or EvidenceExposurePolicy()
        token_delta = self.token_delta
        structured_output = self.structured_output
        tool_call = self.tool_call
        if token_delta is not None:
            token_descriptors = tuple(
                descriptor
                for descriptor in sensitive_fields
                if descriptor.path in ((), ("token_delta",))
            )
            if token_descriptors:
                guarded_token = guard_json_value(
                    {"token_delta": token_delta},
                    tuple(
                        SensitiveFieldDescriptor(("token_delta",), descriptor.field)
                        for descriptor in token_descriptors
                    ),
                    exposure_policy,
                )
                token_value = cast(Mapping[str, JsonValue], guarded_token).get(
                    "token_delta"
                )
                if isinstance(token_value, str):
                    token_delta = token_value
                else:
                    token_delta = "[REDACTED]"
        structured_descriptors = tuple(
            descriptor
            for descriptor in sensitive_fields
            if descriptor.path not in ((), ("token_delta",))
        )
        if structured_descriptors:
            structured_output = guard_json_value(
                structured_output,
                structured_descriptors,
                exposure_policy,
            )
        if tool_call is not None:
            tool_call = tool_call.guarded(sensitive_fields, exposure_policy)
        return replace(
            self,
            token_delta=token_delta,
            structured_output=structured_output,
            tool_call=tool_call,
        )


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
