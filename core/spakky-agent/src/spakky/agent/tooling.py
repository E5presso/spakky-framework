"""Agent tool descriptor discovery contracts."""

import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import MISSING, Field, dataclass, field, is_dataclass
from enum import Enum, StrEnum
from inspect import Parameter, isclass, signature
from types import FunctionType, NoneType, UnionType
from typing import get_args, get_origin, get_type_hints

from spakky.agent.error import AgentDefinitionError
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
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


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
        return cls(data_access=DataAccess.READ_WRITE, externality=Externality.EXTERNAL)


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
class AgentToolSchemaHandle:
    """Stable schema names and generated JSON schemas owned by a descriptor."""

    name: str
    input_schema_name: str
    output_schema_name: str
    input_schema: JsonObject = field(default_factory=dict)
    output_schema: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject blank schema handles."""
        _require_non_blank(self.name, "Agent tool schema name")
        _require_non_blank(self.input_schema_name, "Agent tool input schema name")
        _require_non_blank(self.output_schema_name, "Agent tool output schema name")


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
    """Typed risk, approval, and evidence metadata for a tool descriptor."""

    permissions: tuple[ToolPermission, ...] = ()
    effects: ToolEffects = field(default_factory=ToolEffects)
    idempotency: Idempotency = Idempotency.UNKNOWN
    data_access: DataAccess = DataAccess.NONE
    externality: Externality = Externality.LOCAL
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    result_budget: ResultBudget = field(default_factory=ResultBudget)
    evidence: EvidenceCapture = EvidenceCapture.NONE
    approval: ToolApprovalRequirement = ToolApprovalRequirement.DERIVED


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
    schema = AgentToolSchemaHandle(
        name=definition.schema_name,
        input_schema_name=f"{definition.schema_name}.input",
        output_schema_name=f"{definition.schema_name}.output",
        input_schema=_build_input_schema(function, definition.schema_name),
        output_schema=_build_output_schema(function, definition.schema_name),
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


def _normalize_name(value: str | None, default: str, label: str) -> str:
    candidate = default if value is None else value
    _require_non_blank(candidate, label)
    return candidate


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")


def _build_input_schema(function: FunctionType, schema_name: str) -> JsonObject:
    function_signature = signature(function)
    type_hints = _resolve_type_hints(function)
    properties: dict[str, JsonValue] = {}
    required: list[str] = []
    for parameter in function_signature.parameters.values():
        if parameter.name in ("self", "cls"):
            continue
        _validate_schema_parameter(parameter)
        annotation = type_hints.get(parameter.name, parameter.annotation)
        if annotation == Parameter.empty:
            raise AgentDefinitionError("Agent tool parameters must be type annotated")
        properties[parameter.name] = _schema_for_annotation(
            annotation,
            f"Agent tool parameter '{parameter.name}'",
        )
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
    return schema


def _build_output_schema(function: FunctionType, schema_name: str) -> JsonObject:
    function_signature = signature(function)
    type_hints = _resolve_type_hints(function)
    annotation = type_hints.get("return", function_signature.return_annotation)
    if annotation == Parameter.empty:
        raise AgentDefinitionError("Agent tool return type is required")
    output_schema = _schema_for_annotation(annotation, "Agent tool return type")
    schema: dict[str, JsonValue] = {
        "title": f"{schema_name}.output",
    }
    schema.update(output_schema)
    return schema


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


def _schema_for_annotation(annotation: object, label: str) -> JsonObject:
    annotation = _unwrap_annotated(annotation)
    if annotation is typing.Any:
        raise AgentDefinitionError(f"{label} cannot use Any")
    primitive_schema = _primitive_schema(annotation)
    if primitive_schema is not None:
        return primitive_schema
    origin = get_origin(annotation)
    if origin in (typing.Union, UnionType):
        return _union_schema(annotation, label)
    if origin in (list,):
        return _list_schema(annotation, label)
    if origin is tuple:
        return _tuple_schema(annotation, label)
    if origin in (dict, Mapping):
        return _mapping_schema(annotation, label)
    if isclass(annotation) and issubclass(annotation, Enum):
        return _enum_schema(annotation)
    if isclass(annotation) and is_dataclass(annotation):
        return _dataclass_schema(annotation, label)
    raise AgentDefinitionError(f"{label} is not JSON-schema compatible")


def _unwrap_annotated(annotation: object) -> object:
    if get_origin(annotation) is typing.Annotated:
        return get_args(annotation)[0]
    return annotation


def _primitive_schema(annotation: object) -> JsonObject | None:
    schema_type = _PRIMITIVE_SCHEMA_TYPES.get(annotation)
    if schema_type is None:
        return None
    return {"type": schema_type}


def _union_schema(annotation: object, label: str) -> JsonObject:
    args = get_args(annotation)
    alternatives = [_schema_for_annotation(arg, label) for arg in args]
    return {"anyOf": alternatives}


def _list_schema(annotation: object, label: str) -> JsonObject:
    args = get_args(annotation)
    return {"type": "array", "items": _schema_for_annotation(args[0], label)}


def _tuple_schema(annotation: object, label: str) -> JsonObject:
    args = get_args(annotation)
    if len(args) == 2 and args[1] is Ellipsis:
        return {"type": "array", "items": _schema_for_annotation(args[0], label)}
    prefix_items = [_schema_for_annotation(arg, label) for arg in args]
    return {
        "type": "array",
        "prefixItems": prefix_items,
        "minItems": len(prefix_items),
        "maxItems": len(prefix_items),
    }


def _mapping_schema(annotation: object, label: str) -> JsonObject:
    args = get_args(annotation)
    key_type, value_type = args
    if key_type is not str:
        raise AgentDefinitionError(f"{label} mapping keys must be strings")
    return {
        "type": "object",
        "additionalProperties": _schema_for_annotation(value_type, label),
    }


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


def _dataclass_schema(annotation: object, label: str) -> JsonObject:
    type_hints = _resolve_dataclass_hints(annotation, label)
    properties: dict[str, JsonValue] = {}
    required: list[str] = []
    dataclass_fields = typing.cast(
        Mapping[str, Field[object]],
        vars(annotation)["__dataclass_fields__"],
    )
    for item in dataclass_fields.values():
        field_annotation = type_hints.get(item.name, item.type)
        properties[item.name] = _schema_for_annotation(
            field_annotation,
            f"{label}.{item.name}",
        )
        if item.default is MISSING and item.default_factory is MISSING:
            required.append(item.name)
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _resolve_dataclass_hints(annotation: object, label: str) -> Mapping[str, object]:
    try:
        return get_type_hints(annotation, include_extras=True)
    except (NameError, TypeError) as e:
        raise AgentDefinitionError(
            f"{label} dataclass annotations cannot be resolved"
        ) from e
