"""Provider-neutral agent model port."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from math import isfinite
from typing import Self, cast

from spakky.agent.content import (
    AudioPart,
    DocumentPart,
    ImagePart,
    ModelContent,
    TextPart,
    VideoPart,
    model_content_parts,
    validate_model_content_budget,
)
from spakky.agent.context import (
    ContextDigest,
    ContextManifest,
    ContextManifestEntry,
    ContextPack,
)
from spakky.agent.error import AgentDefinitionError, AgentModelConfigurationError
from spakky.agent.safety import (
    ContextExposurePolicy,
    EvidenceExposurePolicy,
    SensitiveFieldDescriptor,
    guard_json_value,
)
from spakky.agent.types import JsonObject, JsonValue
from spakky.core.common.error import AbstractSpakkyFrameworkError


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
    content: ModelContent
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Snapshot multipart content while preserving canonical plain strings."""
        if not isinstance(self.role, ModelMessageRole):
            raise AgentDefinitionError("Model message role is invalid")
        object.__setattr__(self, "metadata", _snapshot_json_object(self.metadata))
        if isinstance(self.content, str):
            return
        object.__setattr__(self, "content", model_content_parts(self.content))

    @classmethod
    def user(
        cls,
        content: ModelContent,
        *,
        metadata: JsonObject | None = None,
    ) -> Self:
        """Create a user message through the shortest canonical DX."""
        return cls(
            role=ModelMessageRole.USER,
            content=content,
            metadata={} if metadata is None else metadata,
        )


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

    def __post_init__(self) -> None:
        """Deep-freeze tool metadata before provider or cache observation."""
        object.__setattr__(self, "metadata", _snapshot_json_object(self.metadata))


@dataclass(frozen=True, slots=True)
class ToolCallingSpec:
    """Tool calling contract requested from a model adapter."""

    tools: Sequence[ModelToolSpec]
    choice: ModelToolChoice = ModelToolChoice.AUTO

    def __post_init__(self) -> None:
        """Snapshot the ordered tool catalog supplied by a mutable caller."""
        if not isinstance(self.tools, Sequence) or isinstance(
            self.tools,
            str | bytes | bytearray,
        ):
            raise AgentDefinitionError("Model tool catalog must be a sequence")
        tools = tuple(self.tools)
        if any(not isinstance(tool, ModelToolSpec) for tool in tools):
            raise AgentDefinitionError("Model tool catalog contains an invalid tool")
        object.__setattr__(self, "tools", tools)


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
    """Opaque operator-catalog model reference carried by one Agent run."""

    model_ref: str

    def __post_init__(self) -> None:
        """Reject blank catalog references before they reach routing adapters."""
        if self.model_ref.strip() == "":
            raise AgentDefinitionError("Model selection model_ref cannot be blank")


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

    def __post_init__(self) -> None:
        """Deep-snapshot every mutable request input before async adapter work."""
        if not isinstance(self.messages, Sequence) or isinstance(
            self.messages,
            str | bytes | bytearray,
        ):
            raise AgentDefinitionError("Model request messages must be a sequence")
        messages = tuple(self.messages)
        if any(not isinstance(message, ModelMessage) for message in messages):
            raise AgentDefinitionError("Model request contains an invalid message")
        validate_model_content_budget(tuple(message.content for message in messages))
        if not isinstance(self.context, Sequence) or isinstance(
            self.context,
            str | bytes | bytearray,
        ):
            raise AgentDefinitionError("Model request context must be a sequence")
        context = tuple(self.context)
        if any(not isinstance(pack, ContextPack) for pack in context):
            raise AgentDefinitionError("Model request contains an invalid context pack")
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "context", context)
        if self.context_manifest is not None:
            if not isinstance(self.context_manifest, ContextManifest):
                raise AgentDefinitionError("Model request context manifest is invalid")
            _snapshot_context_manifest(self.context_manifest)
        if self.context_digest is not None:
            if not isinstance(self.context_digest, ContextDigest):
                raise AgentDefinitionError("Model request context digest is invalid")
            _snapshot_context_digest(self.context_digest)
        if self.structured_output is not None:
            if not isinstance(self.structured_output, StructuredOutputSpec):
                raise AgentDefinitionError("Model structured output spec is invalid")
        if self.tool_calling is not None:
            if not isinstance(self.tool_calling, ToolCallingSpec):
                raise AgentDefinitionError("Model tool calling spec is invalid")
        object.__setattr__(self, "metadata", _snapshot_json_object(self.metadata))

    def snapshot(self) -> "ModelRequest":
        """Return a deep request copy shared across one async adapter invocation."""
        return ModelRequest(
            messages=tuple(replace(message) for message in self.messages),
            context=tuple(_snapshot_context_pack(pack) for pack in self.context),
            context_manifest=(
                None
                if self.context_manifest is None
                else _snapshot_context_manifest(self.context_manifest)
            ),
            context_digest=(
                None
                if self.context_digest is None
                else _snapshot_context_digest(self.context_digest)
            ),
            structured_output=(
                None
                if self.structured_output is None
                else _snapshot_structured_output(self.structured_output)
            ),
            tool_calling=(
                None
                if self.tool_calling is None
                else _snapshot_tool_calling(self.tool_calling)
            ),
            sampling=self.sampling,
            streaming=self.streaming,
            model_selection=self.model_selection,
            metadata=_snapshot_json_object(self.metadata),
        )

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

    def required_input_modalities(self) -> frozenset["ModelModality"]:
        """Derive every modality present in provider-bound message content."""
        modality_by_type = {
            TextPart: ModelModality.TEXT,
            ImagePart: ModelModality.IMAGE,
            AudioPart: ModelModality.AUDIO,
            VideoPart: ModelModality.VIDEO,
            DocumentPart: ModelModality.DOCUMENT,
        }
        modalities: set[ModelModality] = set()
        for message in self.assemble_messages():
            if isinstance(message.content, str):
                modalities.add(ModelModality.TEXT)
                continue
            for part in model_content_parts(message.content):
                modalities.add(modality_by_type[type(part)])
        return frozenset(modalities)


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Token accounting reported by a model adapter."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    cache_write_5m_input_tokens: int | None = None
    cache_write_1h_input_tokens: int | None = None


class AbstractAgentModelError(AbstractSpakkyFrameworkError, ABC):
    """Model failure that can carry a privacy-safe billable invocation receipt."""

    model_usage: ModelUsage | None
    model_metadata: JsonObject

    def __init__(self) -> None:
        super().__init__()
        self.model_usage = None
        self.model_metadata = {}

    def attach_model_receipt(
        self,
        usage: ModelUsage,
        metadata: JsonObject,
    ) -> None:
        """Attach known usage/routing after provider success but before later failure."""
        if not isinstance(usage, ModelUsage):
            raise AgentDefinitionError("Agent model failure usage is invalid")
        self.model_usage = usage
        self.model_metadata = _snapshot_json_object(metadata)


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


class ModelModality(StrEnum):
    """Portable input and output modalities declared by one model route."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


def _snapshot_context_pack(pack: ContextPack) -> ContextPack:
    return replace(
        pack,
        sensitive_fields=tuple(pack.sensitive_fields),
        metadata=_snapshot_json_object(pack.metadata),
    )


def _snapshot_context_manifest(manifest: ContextManifest) -> ContextManifest:
    if not isinstance(manifest.entries, Sequence) or isinstance(
        manifest.entries,
        str | bytes | bytearray,
    ):
        raise AgentDefinitionError("Model context manifest entries are invalid")
    entries = tuple(manifest.entries)
    if any(not isinstance(entry, ContextManifestEntry) for entry in entries):
        raise AgentDefinitionError("Model context manifest entry is invalid")
    if not isinstance(manifest.evidence_refs, Sequence) or isinstance(
        manifest.evidence_refs,
        str | bytes | bytearray,
    ):
        raise AgentDefinitionError("Model context manifest evidence refs are invalid")
    return replace(
        manifest,
        entries=tuple(
            replace(
                entry,
                sensitive_fields=tuple(entry.sensitive_fields),
                metadata=_snapshot_json_object(entry.metadata),
            )
            for entry in entries
        ),
        evidence_refs=tuple(manifest.evidence_refs),
        metadata=_snapshot_json_object(manifest.metadata),
    )


def _snapshot_context_digest(digest: ContextDigest) -> ContextDigest:
    if not isinstance(digest.derived_from_pack_ids, Sequence) or isinstance(
        digest.derived_from_pack_ids,
        str | bytes | bytearray,
    ):
        raise AgentDefinitionError("Model context digest pack refs are invalid")
    return replace(
        digest,
        derived_from_pack_ids=tuple(digest.derived_from_pack_ids),
        metadata=_snapshot_json_object(digest.metadata),
    )


def _snapshot_structured_output(spec: StructuredOutputSpec) -> StructuredOutputSpec:
    return replace(
        spec,
        constraint=replace(
            spec.constraint,
            schema=_snapshot_json_object(spec.constraint.schema),
        ),
    )


def _snapshot_tool_calling(spec: ToolCallingSpec) -> ToolCallingSpec:
    return replace(
        spec,
        tools=tuple(
            replace(
                tool,
                parameters=replace(
                    tool.parameters,
                    schema=_snapshot_json_object(tool.parameters.schema),
                ),
                metadata=_snapshot_json_object(tool.metadata),
            )
            for tool in spec.tools
        ),
    )


def _snapshot_json_object(value: object) -> JsonObject:
    snapshot = _snapshot_json(value)
    if not isinstance(snapshot, Mapping):
        raise AgentDefinitionError("Model JSON object is invalid")
    return snapshot


def _snapshot_json(value: object) -> JsonValue:
    try:
        return _freeze_json(value)
    except RecursionError as error:
        raise AgentDefinitionError("Model JSON value cannot be recursive") from error


def _freeze_json(value: object) -> JsonValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise AgentDefinitionError("Model JSON number must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentDefinitionError("Model JSON object key must be text")
            frozen[key] = _freeze_json(item)
        return frozen
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        items = [_freeze_json(item) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    raise AgentDefinitionError("Model JSON value is invalid")


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Provider-neutral declaration of a model backend's queryable abilities.

    The agent runner consults this descriptor before a run to adjust behaviour
    without invoking the backend. Input/output modalities default to text only,
    while tool calling and structured output default to unsupported. Reasoning,
    context-window size, and token-counting support remain explicit so routing
    adapters can expose the exact abilities of each logical model route.
    """

    supports_reasoning: bool = False
    context_window_tokens: int | None = None
    supports_token_counting: bool = False
    input_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})
    output_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})
    supports_tools: bool = False
    supports_structured_output: bool = False


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

    def validate_request(self, request: ModelRequest) -> None:
        """Fail before provider I/O when this model cannot honor the request."""
        if not isinstance(request, ModelRequest):
            raise AgentDefinitionError("Agent model request is invalid")
        capability = self.capability_for(request.model_selection)
        if not isinstance(capability, ModelCapability):
            raise AgentModelConfigurationError(
                "Agent model capability descriptor is invalid"
            )
        if not request.required_input_modalities() <= capability.input_modalities:
            raise AgentModelConfigurationError(
                "Agent model does not support every requested input modality"
            )

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a complete model response for the request."""
        ...

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Return provider-neutral stream events for the request."""
        ...
