"""Agent tool descriptor discovery contracts."""

import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import MISSING, Field, dataclass, field, is_dataclass
from enum import Enum, StrEnum
from inspect import Parameter, Signature, isclass, signature
from types import FunctionType, NoneType, UnionType
from typing import get_args, get_origin, get_type_hints

from spakky.agent.error import AgentDefinitionError, AgentToolBindingError
from spakky.agent.safety import (
    ContextExposurePolicy,
    SecretField,
    SensitiveField,
    SensitiveFieldDescriptor,
    schema_with_sensitive_metadata,
)
from spakky.agent.types import JsonObject, JsonValue

AGENT_TOOL_DEFINITION_KEY = "__spakky_agent_tool_definition__"

AgentToolCallable = Callable[..., object]

_PRIMITIVE_SCHEMA_TYPES: dict[object, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    NoneType: "null",
}


class Idempotency(StrEnum):
    """Action idempotency declared by a tool."""

    IDEMPOTENT = "idempotent"
    CONDITIONALLY_IDEMPOTENT = "conditionally_idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


class ToolResumeAction(StrEnum):
    """Resume action allowed by stored tool idempotency metadata."""

    RETRY = "retry"
    REQUIRE_APPROVAL = "require_approval"
    SKIP_COMPLETED = "skip_completed"


class DataAccess(StrEnum):
    """Data access level declared by a tool."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"


class Externality(StrEnum):
    """External side-effect boundary declared by a tool."""

    LOCAL = "local"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class EvidenceCapture(StrEnum):
    """Evidence capture strategy for tool results."""

    NONE = "none"
    REFERENCE_ONLY = "reference_only"
    SUMMARY = "summary"
    STRUCTURED = "structured"
    RAW = "raw"
    REDACTED = "redacted"


class ToolApprovalRequirement(StrEnum):
    """Human approval requirement at the tool boundary."""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    DERIVED = "derived"


class ToolRiskAxis(StrEnum):
    """Derived risk axes exposed for policy and UI decisions."""

    READ = "read"
    WRITE = "write"
    SIDE_EFFECT = "side_effect"
    DESTRUCTIVE = "destructive"
    NETWORK = "network"


@dataclass(frozen=True, slots=True)
class ToolPermission:
    """Typed permission marker attached to a tool descriptor."""

    name: str

    def __post_init__(self) -> None:
        """Reject permission names that cannot be matched deterministically."""
        if not self.name.strip():
            raise AgentDefinitionError("Agent tool permission name cannot be blank")


@dataclass(frozen=True, slots=True)
class ToolEffects:
    """Typed effect metadata used to derive display risk outside core."""

    data_access: DataAccess = DataAccess.NONE
    externality: Externality = Externality.LOCAL
    destructive: bool = False
    network: bool = False

    @classmethod
    def read_only(cls) -> "ToolEffects":
        """Declare a local read-only tool."""
        return cls(data_access=DataAccess.READ, externality=Externality.LOCAL)

    @classmethod
    def write_state(cls) -> "ToolEffects":
        """Declare a local state-writing tool."""
        return cls(data_access=DataAccess.WRITE, externality=Externality.LOCAL)

    @classmethod
    def external_side_effect(cls) -> "ToolEffects":
        """Declare a tool that crosses an external side-effect boundary."""
        return cls(
            data_access=DataAccess.READ_WRITE,
            externality=Externality.EXTERNAL,
            network=True,
        )

    @classmethod
    def destructive_action(cls) -> "ToolEffects":
        """Declare a tool that may irreversibly mutate local or external state."""
        return cls(
            data_access=DataAccess.WRITE,
            externality=Externality.EXTERNAL,
            destructive=True,
        )


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """Optional timeout boundary for a tool invocation."""

    seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject non-positive timeout policies at definition time."""
        if self.seconds is not None and self.seconds <= 0:
            raise AgentDefinitionError("Agent tool timeout must be positive")


@dataclass(frozen=True, slots=True)
class ResultBudget:
    """Optional result-size budget for model-facing tool output."""

    max_bytes: int | None = None

    def __post_init__(self) -> None:
        """Reject result budgets that cannot constrain output."""
        if self.max_bytes is not None and self.max_bytes <= 0:
            raise AgentDefinitionError("Agent tool result budget must be positive")


@dataclass(frozen=True, slots=True)
class ToolResumeMetadata:
    """Stored idempotency metadata used when resuming an incomplete action."""

    idempotency: Idempotency = Idempotency.UNKNOWN

    @classmethod
    def from_metadata(cls, metadata: "AgentToolMetadata") -> "ToolResumeMetadata":
        """Build resume metadata from a tool descriptor metadata object."""
        return cls(idempotency=metadata.idempotency)

    def action_for_completed_boundary(self) -> ToolResumeAction:
        """Return the resume action for an already completed action boundary."""
        return ToolResumeAction.SKIP_COMPLETED

    def action_for_incomplete_boundary(self) -> ToolResumeAction:
        """Return the resume action for an incomplete action boundary."""
        if self.idempotency in (
            Idempotency.IDEMPOTENT,
            Idempotency.CONDITIONALLY_IDEMPOTENT,
        ):
            return ToolResumeAction.RETRY
        return ToolResumeAction.REQUIRE_APPROVAL


@dataclass(frozen=True, slots=True)
class AgentToolSchemaHandle:
    """Stable schema names and generated JSON schemas owned by a descriptor."""

    name: str
    input_schema_name: str
    output_schema_name: str
    input_schema: JsonObject = field(default_factory=dict)
    output_schema: JsonObject = field(default_factory=dict)
    input_sensitive_fields: tuple[SensitiveFieldDescriptor, ...] = ()
    output_sensitive_fields: tuple[SensitiveFieldDescriptor, ...] = ()

    def __post_init__(self) -> None:
        """Reject blank schema handles."""
        _require_non_blank(self.name, "Agent tool schema name")
        _require_non_blank(self.input_schema_name, "Agent tool input schema name")
        _require_non_blank(self.output_schema_name, "Agent tool output schema name")

    def input_schema_for(
        self,
        policy: ContextExposurePolicy | None = None,
    ) -> JsonObject:
        """Return model-facing input schema under the requested exposure policy."""
        return schema_with_sensitive_metadata(
            self.input_schema,
            self.input_sensitive_fields,
            policy or ContextExposurePolicy(),
        )

    def output_schema_for(
        self,
        policy: ContextExposurePolicy | None = None,
    ) -> JsonObject:
        """Return model-facing output schema under the requested exposure policy."""
        return schema_with_sensitive_metadata(
            self.output_schema,
            self.output_sensitive_fields,
            policy or ContextExposurePolicy(),
        )


@dataclass(frozen=True, slots=True)
class AgentToolIdentity:
    """Descriptor identity independent from free-form model output text."""

    owner_module: str
    owner_qualname: str
    name: str

    def __post_init__(self) -> None:
        """Reject identity parts that cannot be serialized or matched."""
        _require_non_blank(self.owner_module, "Agent tool owner module")
        _require_non_blank(self.owner_qualname, "Agent tool owner qualname")
        _require_non_blank(self.name, "Agent tool name")

    @property
    def key(self) -> str:
        """Return a stable key for maps, logs, and evidence metadata."""
        return f"{self.owner_module}.{self.owner_qualname}:{self.name}"


@dataclass(frozen=True, slots=True)
class AgentToolMetadata:
    """Typed approval, idempotency, and evidence metadata for a descriptor."""

    permissions: tuple[ToolPermission, ...] = ()
    effects: ToolEffects = field(default_factory=ToolEffects)
    idempotency: Idempotency = Idempotency.UNKNOWN
    data_access: DataAccess = DataAccess.NONE
    externality: Externality = Externality.LOCAL
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    result_budget: ResultBudget = field(default_factory=ResultBudget)
    evidence: EvidenceCapture = EvidenceCapture.NONE
    approval: ToolApprovalRequirement = ToolApprovalRequirement.DERIVED

    @property
    def risk(self) -> "ToolRisk":
        """Return derived risk axes without storing risk as source metadata."""
        return ToolRisk.from_metadata(self)

    @property
    def resume(self) -> ToolResumeMetadata:
        """Return resume metadata derived from stored idempotency."""
        return ToolResumeMetadata.from_metadata(self)

    @property
    def requires_approval_candidate(self) -> bool:
        """Return whether this tool is a HITL approval candidate."""
        if self.approval == ToolApprovalRequirement.REQUIRED:
            return True
        if self.approval == ToolApprovalRequirement.NOT_REQUIRED:
            return False
        return self.risk.requires_approval_candidate


@dataclass(frozen=True, slots=True)
class ToolRisk:
    """Derived typed risk axes for policy and evidence annotations."""

    axes: tuple[ToolRiskAxis, ...] = ()

    def __post_init__(self) -> None:
        """Reject duplicate axes so risk comparisons stay deterministic."""
        seen: set[ToolRiskAxis] = set()
        for axis in self.axes:
            if axis in seen:
                raise AgentDefinitionError("Agent tool risk axes must be unique")
            seen.add(axis)

    @classmethod
    def from_metadata(cls, metadata: AgentToolMetadata) -> "ToolRisk":
        """Derive risk axes from source tool metadata."""
        axes: list[ToolRiskAxis] = []
        if metadata.data_access in (DataAccess.READ, DataAccess.READ_WRITE):
            axes.append(ToolRiskAxis.READ)
        if metadata.data_access in (DataAccess.WRITE, DataAccess.READ_WRITE):
            axes.append(ToolRiskAxis.WRITE)
        if metadata.data_access in (DataAccess.WRITE, DataAccess.READ_WRITE):
            axes.append(ToolRiskAxis.SIDE_EFFECT)
        if metadata.externality in (Externality.EXTERNAL, Externality.UNKNOWN):
            axes.append(ToolRiskAxis.SIDE_EFFECT)
        if metadata.effects.destructive:
            axes.append(ToolRiskAxis.DESTRUCTIVE)
        if metadata.effects.network or metadata.externality == Externality.EXTERNAL:
            axes.append(ToolRiskAxis.NETWORK)
        return cls(axes=_deduplicate_axes(axes))

    @property
    def requires_approval_candidate(self) -> bool:
        """Return whether the risk is strong enough to suggest HITL approval."""
        if self.includes(ToolRiskAxis.DESTRUCTIVE):
            return True
        return self.includes(ToolRiskAxis.SIDE_EFFECT) and (
            self.includes(ToolRiskAxis.WRITE) or self.includes(ToolRiskAxis.NETWORK)
        )

    def includes(self, axis: ToolRiskAxis) -> bool:
        """Return whether this risk contains the requested axis."""
        return axis in self.axes


@dataclass(frozen=True, slots=True)
class AgentToolDefinition:
    """Method-level metadata attached by @agent_tool before owner discovery."""

    name: str
    schema_name: str
    description: str | None = None
    metadata: AgentToolMetadata = field(default_factory=AgentToolMetadata)

    def __post_init__(self) -> None:
        """Reject definitions that would make catalog lookup ambiguous."""
        _require_non_blank(self.name, "Agent tool name")
        _require_non_blank(self.schema_name, "Agent tool schema name")
        if self.description is not None and not self.description.strip():
            raise AgentDefinitionError("Agent tool description cannot be blank")


@dataclass(frozen=True, slots=True)
class AgentToolDescriptor:
    """Discovered tool descriptor bound to an owner class and callable."""

    identity: AgentToolIdentity
    owner: type[object]
    callable: AgentToolCallable
    schema: AgentToolSchemaHandle
    description: str | None = None
    metadata: AgentToolMetadata = field(default_factory=AgentToolMetadata)

    @property
    def name(self) -> str:
        """Return the descriptor-local tool name."""
        return self.identity.name

    def bind_invocation(self, payload: JsonObject) -> "AgentToolBoundInvocation":
        """Bind a decoded model payload before the tool callable is invoked."""
        return bind_agent_tool_invocation(self.callable, payload)


@dataclass(frozen=True, slots=True)
class AgentToolBoundInvocation:
    """Python-call-ready tool invocation arguments."""

    args: tuple[object, ...] = ()
    kwargs: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentToolCatalog:
    """Deterministic catalog of descriptors discovered from an Agent class."""

    descriptors: tuple[AgentToolDescriptor, ...] = ()

    def __post_init__(self) -> None:
        """Reject duplicate identity or schema names before model lookup."""
        identity_keys: set[str] = set()
        schema_names: set[str] = set()
        for descriptor in self.descriptors:
            if descriptor.identity.key in identity_keys:
                raise AgentDefinitionError("Agent tool identity must be unique")
            if descriptor.schema.name in schema_names:
                raise AgentDefinitionError("Agent tool schema name must be unique")
            identity_keys.add(descriptor.identity.key)
            schema_names.add(descriptor.schema.name)

    def by_identity(self, identity: AgentToolIdentity) -> AgentToolDescriptor:
        """Lookup a descriptor by typed identity."""
        for descriptor in self.descriptors:
            if descriptor.identity == identity:
                return descriptor
        raise AgentDefinitionError("Agent tool identity is not registered")

    def by_schema_name(self, schema_name: str) -> AgentToolDescriptor:
        """Lookup a descriptor by model-facing schema name."""
        _require_non_blank(schema_name, "Agent tool schema name")
        for descriptor in self.descriptors:
            if descriptor.schema.name == schema_name:
                return descriptor
        raise AgentDefinitionError("Agent tool schema name is not registered")


def agent_tool(
    *,
    name: str | None = None,
    schema_name: str | None = None,
    description: str | None = None,
    permissions: Sequence[ToolPermission] = (),
    effects: ToolEffects | None = None,
    idempotency: Idempotency = Idempotency.UNKNOWN,
    data_access: DataAccess | None = None,
    externality: Externality | None = None,
    timeout: TimeoutPolicy | None = None,
    result_budget: ResultBudget | None = None,
    evidence: EvidenceCapture = EvidenceCapture.NONE,
    approval: ToolApprovalRequirement = ToolApprovalRequirement.DERIVED,
) -> Callable[[FunctionType], FunctionType]:
    """Attach typed agent-tool metadata to a method object."""

    def decorate(function: FunctionType) -> FunctionType:
        tool_name = _normalize_name(name, function.__name__, "Agent tool name")
        normalized_schema_name = _normalize_name(
            schema_name,
            tool_name,
            "Agent tool schema name",
        )
        tool_effects = effects or ToolEffects()
        metadata = AgentToolMetadata(
            permissions=tuple(permissions),
            effects=tool_effects,
            idempotency=idempotency,
            data_access=data_access or tool_effects.data_access,
            externality=externality or tool_effects.externality,
            timeout=timeout or TimeoutPolicy(),
            result_budget=result_budget or ResultBudget(),
            evidence=evidence,
            approval=approval,
        )
        definition = AgentToolDefinition(
            name=tool_name,
            schema_name=normalized_schema_name,
            description=description,
            metadata=metadata,
        )
        function.__dict__[AGENT_TOOL_DEFINITION_KEY] = definition
        return function

    return decorate


def discover_agent_tools(owner: type[object]) -> AgentToolCatalog:
    """Discover @agent_tool methods in deterministic class-definition order."""
    descriptors: list[AgentToolDescriptor] = []
    resolved_member_names: set[str] = set()
    for declaring_owner in owner.__mro__:
        if declaring_owner is object:
            continue
        for member_name, member in vars(declaring_owner).items():
            if member_name in resolved_member_names:
                continue
            resolved_member_names.add(member_name)
            function = _unwrap_function(member)
            if function is None:
                continue
            definition = get_agent_tool_definition(function)
            if definition is None:
                continue
            descriptors.append(
                _build_descriptor(declaring_owner, function, definition),
            )
    ordered = tuple(
        sorted(
            descriptors,
            key=lambda descriptor: descriptor.identity.key,
        ),
    )
    return AgentToolCatalog(descriptors=ordered)


def get_agent_tool_definition(
    function: FunctionType,
) -> AgentToolDefinition | None:
    """Return decorator metadata attached to a function object."""
    candidate = vars(function).get(AGENT_TOOL_DEFINITION_KEY)
    if candidate is None:
        return None
    if not isinstance(candidate, AgentToolDefinition):
        raise AgentDefinitionError("Agent tool metadata is invalid")
    return candidate


def bind_agent_tool_invocation(
    function: AgentToolCallable,
    payload: JsonObject,
) -> AgentToolBoundInvocation:
    """Bind a structured model payload to a tool function signature."""
    invocation = _parse_invocation_payload(payload)
    try:
        function_signature = signature(function)
    except (TypeError, ValueError) as e:
        raise AgentToolBindingError(
            "Agent tool callable signature cannot be inspected"
        ) from e
    call_signature = _drop_owner_parameter(function_signature)
    try:
        bound = call_signature.bind(*invocation.args, **invocation.kwargs)
    except TypeError as e:
        raise AgentToolBindingError(
            "Agent tool invocation payload cannot be bound"
        ) from e
    bound.apply_defaults()
    return AgentToolBoundInvocation(
        args=tuple(bound.args),
        kwargs=dict(bound.kwargs),
    )


def _build_descriptor(
    owner: type[object],
    function: FunctionType,
    definition: AgentToolDefinition,
) -> AgentToolDescriptor:
    identity = AgentToolIdentity(
        owner_module=owner.__module__,
        owner_qualname=owner.__qualname__,
        name=definition.name,
    )
    input_schema = _build_input_schema(function, definition.schema_name)
    output_schema = _build_output_schema(function, definition.schema_name)
    schema = AgentToolSchemaHandle(
        name=definition.schema_name,
        input_schema_name=f"{definition.schema_name}.input",
        output_schema_name=f"{definition.schema_name}.output",
        input_schema=input_schema.schema,
        output_schema=output_schema.schema,
        input_sensitive_fields=input_schema.sensitive_fields,
        output_sensitive_fields=output_schema.sensitive_fields,
    )
    return AgentToolDescriptor(
        identity=identity,
        owner=owner,
        callable=function,
        schema=schema,
        description=definition.description,
        metadata=definition.metadata,
    )


def _unwrap_function(member: object) -> FunctionType | None:
    if isinstance(member, (staticmethod, classmethod)):
        member = member.__func__
    if isinstance(member, FunctionType):
        return member
    return None


@dataclass(frozen=True, slots=True)
class _StructuredInvocationPayload:
    args: tuple[object, ...]
    kwargs: Mapping[str, object]


def _parse_invocation_payload(payload: JsonObject) -> _StructuredInvocationPayload:
    payload_dict = _copy_string_key_mapping(
        payload,
        "Agent tool invocation payload",
    )
    if "args" in payload_dict or "kwargs" in payload_dict:
        return _parse_args_kwargs_payload(payload_dict)
    return _StructuredInvocationPayload(args=(), kwargs=payload_dict)


def _parse_args_kwargs_payload(
    payload: Mapping[str, object],
) -> _StructuredInvocationPayload:
    extra_keys = set(payload) - {"args", "kwargs"}
    if extra_keys:
        raise AgentToolBindingError(
            "Agent tool structured invocation payload cannot mix direct arguments"
        )
    args = _payload_args(payload.get("args", ()))
    kwargs = _payload_kwargs(payload.get("kwargs", {}))
    return _StructuredInvocationPayload(args=args, kwargs=kwargs)


def _payload_args(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise AgentToolBindingError("Agent tool invocation args must be an array")
    return tuple(value)


def _payload_kwargs(value: object) -> Mapping[str, object]:
    return _copy_string_key_mapping(value, "Agent tool invocation kwargs")


def _copy_string_key_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise AgentToolBindingError(f"{label} must be an object")
    result: dict[str, object] = {}
    for key in value:
        if not isinstance(key, str):
            raise AgentToolBindingError(f"{label} keys must be strings")
        result[key] = value[key]
    return result


def _drop_owner_parameter(function_signature: Signature) -> Signature:
    parameters = tuple(function_signature.parameters.values())
    if parameters and parameters[0].name in ("self", "cls"):
        parameters = parameters[1:]
    return function_signature.replace(parameters=parameters)


def _normalize_name(value: str | None, default: str, label: str) -> str:
    candidate = default if value is None else value
    _require_non_blank(candidate, label)
    return candidate


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")


@dataclass(frozen=True, slots=True)
class _SchemaExtraction:
    schema: JsonObject
    sensitive_fields: tuple[SensitiveFieldDescriptor, ...] = ()


def _build_input_schema(function: FunctionType, schema_name: str) -> _SchemaExtraction:
    function_signature = signature(function)
    type_hints = _resolve_type_hints(function)
    properties: dict[str, JsonValue] = {}
    required: list[str] = []
    sensitive_fields: list[SensitiveFieldDescriptor] = []
    for parameter in function_signature.parameters.values():
        if parameter.name in ("self", "cls"):
            continue
        _validate_schema_parameter(parameter)
        annotation = type_hints.get(parameter.name, parameter.annotation)
        if annotation == Parameter.empty:
            raise AgentDefinitionError("Agent tool parameters must be type annotated")
        extracted = _schema_for_annotation(
            annotation,
            f"Agent tool parameter '{parameter.name}'",
            (parameter.name,),
        )
        properties[parameter.name] = extracted.schema
        sensitive_fields.extend(extracted.sensitive_fields)
        if parameter.default == Parameter.empty:
            required.append(parameter.name)
    schema: dict[str, JsonValue] = {
        "type": "object",
        "title": f"{schema_name}.input",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return _SchemaExtraction(schema=schema, sensitive_fields=tuple(sensitive_fields))


def _build_output_schema(function: FunctionType, schema_name: str) -> _SchemaExtraction:
    function_signature = signature(function)
    type_hints = _resolve_type_hints(function)
    annotation = type_hints.get("return", function_signature.return_annotation)
    if annotation == Parameter.empty:
        raise AgentDefinitionError("Agent tool return type is required")
    output_schema = _schema_for_annotation(annotation, "Agent tool return type", ())
    schema: dict[str, JsonValue] = {
        "title": f"{schema_name}.output",
    }
    schema.update(output_schema.schema)
    return _SchemaExtraction(
        schema=schema,
        sensitive_fields=output_schema.sensitive_fields,
    )


def _resolve_type_hints(function: FunctionType) -> Mapping[str, object]:
    try:
        return get_type_hints(function, include_extras=True)
    except (NameError, TypeError) as e:
        raise AgentDefinitionError(
            "Agent tool type annotations cannot be resolved"
        ) from e


def _validate_schema_parameter(parameter: Parameter) -> None:
    if parameter.kind == Parameter.POSITIONAL_ONLY:
        raise AgentDefinitionError("Agent tool parameters cannot be positional-only")
    if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
        raise AgentDefinitionError(
            "Agent tool parameters cannot use variable arguments"
        )


def _schema_for_annotation(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    annotation, annotated_sensitive_fields = _unwrap_annotated(annotation, path)
    if annotation is typing.Any:
        raise AgentDefinitionError(f"{label} cannot use Any")
    primitive_schema = _primitive_schema(annotation)
    if primitive_schema is not None:
        return _SchemaExtraction(
            schema=primitive_schema,
            sensitive_fields=annotated_sensitive_fields,
        )
    origin = get_origin(annotation)
    if origin in (typing.Union, UnionType):
        return _merge_annotated_fields(
            _union_schema(annotation, label, path),
            annotated_sensitive_fields,
        )
    if origin in (list,):
        return _merge_annotated_fields(
            _list_schema(annotation, label, path),
            annotated_sensitive_fields,
        )
    if origin is tuple:
        return _merge_annotated_fields(
            _tuple_schema(annotation, label, path),
            annotated_sensitive_fields,
        )
    if origin in (dict, Mapping):
        return _merge_annotated_fields(
            _mapping_schema(annotation, label, path),
            annotated_sensitive_fields,
        )
    if isclass(annotation) and issubclass(annotation, Enum):
        return _SchemaExtraction(
            schema=_enum_schema(annotation),
            sensitive_fields=annotated_sensitive_fields,
        )
    if isclass(annotation) and is_dataclass(annotation):
        return _merge_annotated_fields(
            _dataclass_schema(annotation, label, path),
            annotated_sensitive_fields,
        )
    raise AgentDefinitionError(f"{label} is not JSON-schema compatible")


def _unwrap_annotated(
    annotation: object,
    path: tuple[str, ...],
) -> tuple[object, tuple[SensitiveFieldDescriptor, ...]]:
    if get_origin(annotation) is typing.Annotated:
        args = get_args(annotation)
        sensitive_fields = tuple(
            SensitiveFieldDescriptor(path, metadata)
            for metadata in args[1:]
            if isinstance(metadata, (SensitiveField, SecretField))
        )
        return args[0], sensitive_fields
    return annotation, ()


def _primitive_schema(annotation: object) -> JsonObject | None:
    schema_type = _PRIMITIVE_SCHEMA_TYPES.get(annotation)
    if schema_type is None:
        return None
    return {"type": schema_type}


def _union_schema(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    args = get_args(annotation)
    alternatives = tuple(_schema_for_annotation(arg, label, path) for arg in args)
    return _SchemaExtraction(
        schema={"anyOf": [extracted.schema for extracted in alternatives]},
        sensitive_fields=tuple(
            descriptor
            for extracted in alternatives
            for descriptor in extracted.sensitive_fields
        ),
    )


def _list_schema(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    args = get_args(annotation)
    item = _schema_for_annotation(args[0], label, path)
    return _SchemaExtraction(
        schema={"type": "array", "items": item.schema},
        sensitive_fields=item.sensitive_fields,
    )


def _tuple_schema(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    args = get_args(annotation)
    if len(args) == 2 and args[1] is Ellipsis:
        item = _schema_for_annotation(args[0], label, path)
        return _SchemaExtraction(
            schema={"type": "array", "items": item.schema},
            sensitive_fields=item.sensitive_fields,
        )
    prefix_items = tuple(_schema_for_annotation(arg, label, path) for arg in args)
    return _SchemaExtraction(
        schema={
            "type": "array",
            "prefixItems": [extracted.schema for extracted in prefix_items],
            "minItems": len(prefix_items),
            "maxItems": len(prefix_items),
        },
        sensitive_fields=tuple(
            descriptor
            for extracted in prefix_items
            for descriptor in extracted.sensitive_fields
        ),
    )


def _mapping_schema(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    args = get_args(annotation)
    key_type, value_type = args
    if key_type is not str:
        raise AgentDefinitionError(f"{label} mapping keys must be strings")
    value = _schema_for_annotation(value_type, label, path)
    return _SchemaExtraction(
        schema={
            "type": "object",
            "additionalProperties": value.schema,
        },
        sensitive_fields=value.sensitive_fields,
    )


def _enum_schema(annotation: type[Enum]) -> JsonObject:
    values: list[JsonValue] = []
    value_types: set[str] = set()
    for member in annotation:
        value = member.value
        value_type = _json_value_type(value)
        if value_type is None:
            raise AgentDefinitionError("Agent tool enum values must be JSON primitives")
        values.append(value)
        value_types.add(value_type)
    schema: dict[str, JsonValue] = {"enum": values}
    if len(value_types) == 1:
        schema["type"] = next(iter(value_types))
    return schema


def _json_value_type(value: object) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return None


def _dataclass_schema(
    annotation: object,
    label: str,
    path: tuple[str, ...],
) -> _SchemaExtraction:
    type_hints = _resolve_dataclass_hints(annotation, label)
    properties: dict[str, JsonValue] = {}
    required: list[str] = []
    sensitive_fields: list[SensitiveFieldDescriptor] = []
    dataclass_fields = typing.cast(
        Mapping[str, Field[object]],
        vars(annotation)["__dataclass_fields__"],
    )
    for item in dataclass_fields.values():
        field_annotation = type_hints.get(item.name, item.type)
        extracted = _schema_for_annotation(
            field_annotation,
            f"{label}.{item.name}",
            (*path, item.name),
        )
        properties[item.name] = extracted.schema
        sensitive_fields.extend(extracted.sensitive_fields)
        if item.default is MISSING and item.default_factory is MISSING:
            required.append(item.name)
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return _SchemaExtraction(schema=schema, sensitive_fields=tuple(sensitive_fields))


def _merge_annotated_fields(
    extraction: _SchemaExtraction,
    annotated_sensitive_fields: tuple[SensitiveFieldDescriptor, ...],
) -> _SchemaExtraction:
    return _SchemaExtraction(
        schema=extraction.schema,
        sensitive_fields=(
            *annotated_sensitive_fields,
            *extraction.sensitive_fields,
        ),
    )


def _resolve_dataclass_hints(annotation: object, label: str) -> Mapping[str, object]:
    try:
        return get_type_hints(annotation, include_extras=True)
    except (NameError, TypeError) as e:
        raise AgentDefinitionError(
            f"{label} dataclass annotations cannot be resolved"
        ) from e


def _deduplicate_axes(axes: Sequence[ToolRiskAxis]) -> tuple[ToolRiskAxis, ...]:
    ordered: list[ToolRiskAxis] = []
    for axis in axes:
        if axis not in ordered:
            ordered.append(axis)
    return tuple(ordered)
