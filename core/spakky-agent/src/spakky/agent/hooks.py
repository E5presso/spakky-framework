"""Declarative signal-hook discovery contracts (ADR-0013 §1).

The framework runner owns the execution loop, but a developer still needs a
declarative seam to react to inbound signals (a steering instruction, an
external event, a user message) and emit their own stream items without writing
a loop body. ``@on_signal(kind)`` is that seam: it marks a coroutine generator
method the same way ``@agent_tool`` marks a tool method, and the runner invokes
every matching hook when it consumes a signal of that kind at a poll point.

Discovery mirrors ``discover_agent_tools`` exactly — an MRO walk reading
``vars()`` (not the banned ``getattr``) so the raw function objects are found
before descriptor binding — so the two declarative seams stay structurally
identical for a reader.
"""

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from inspect import Parameter, Signature, isasyncgenfunction, signature
from types import FunctionType
from typing import get_args, get_origin, get_type_hints

from spakky.agent.error import AgentDefinitionError
from spakky.agent.signal import AgentSignal, AgentSignalKind
from spakky.agent.yield_ import AgentYield

AGENT_SIGNAL_HOOK_DEFINITION_KEY = "__spakky_agent_signal_hook_definition__"

AgentSignalHookCallable = Callable[..., AsyncGenerator[AgentYield[object], None]]


@dataclass(frozen=True, slots=True)
class AgentSignalHookDefinition:
    """Method-level metadata attached by ``@on_signal`` before owner discovery."""

    kind: AgentSignalKind


@dataclass(frozen=True, slots=True)
class AgentSignalHookIdentity:
    """Hook identity independent from the developer-chosen method name."""

    owner_module: str
    owner_qualname: str
    member_name: str

    @property
    def key(self) -> str:
        """Return a stable key for deterministic ordering and logs."""
        return f"{self.owner_module}.{self.owner_qualname}:{self.member_name}"


@dataclass(frozen=True, slots=True)
class AgentSignalHookDescriptor:
    """Discovered signal hook bound to an owner class and callable."""

    identity: AgentSignalHookIdentity
    owner: type[object]
    callable: AgentSignalHookCallable
    kind: AgentSignalKind


@dataclass(frozen=True, slots=True)
class AgentSignalHookCatalog:
    """Deterministic catalog of signal hooks discovered from an Agent class."""

    descriptors: tuple[AgentSignalHookDescriptor, ...] = ()

    def __post_init__(self) -> None:
        """Reject duplicate hook identities so dispatch order stays stable."""
        identity_keys: set[str] = set()
        for descriptor in self.descriptors:
            if descriptor.identity.key in identity_keys:
                raise AgentDefinitionError("Agent signal hook identity must be unique")
            identity_keys.add(descriptor.identity.key)

    def hooks_for(
        self,
        kind: AgentSignalKind,
    ) -> tuple[AgentSignalHookDescriptor, ...]:
        """Return every hook that handles the requested signal kind, in order."""
        return tuple(
            descriptor for descriptor in self.descriptors if descriptor.kind is kind
        )


def on_signal(kind: AgentSignalKind) -> Callable[[FunctionType], FunctionType]:
    """Declare a method that reacts to one inbound signal kind.

    The decorated method must be an async generator yielding ``AgentYield``
    items and accepting exactly one ``signal: AgentSignal`` argument besides
    ``self``. The runner invokes it when it consumes a signal of ``kind`` at a
    poll point, and forwards every yielded item into the public stream.
    """

    def decorate(function: FunctionType) -> FunctionType:
        function.__dict__[AGENT_SIGNAL_HOOK_DEFINITION_KEY] = AgentSignalHookDefinition(
            kind=kind,
        )
        return function

    return decorate


def discover_agent_signal_hooks(owner: type[object]) -> AgentSignalHookCatalog:
    """Discover ``@on_signal`` methods in deterministic class-definition order."""
    descriptors: list[AgentSignalHookDescriptor] = []
    resolved_member_names: set[str] = set()
    for declaring_owner in owner.__mro__:
        if declaring_owner is object:
            continue
        for member_name, member in vars(declaring_owner).items():
            if member_name in resolved_member_names:
                continue
            resolved_member_names.add(member_name)
            if not isinstance(member, FunctionType):
                continue
            definition = _get_signal_hook_definition(member)
            if definition is None:
                continue
            _validate_hook_contract(member)
            descriptors.append(
                AgentSignalHookDescriptor(
                    identity=AgentSignalHookIdentity(
                        owner_module=declaring_owner.__module__,
                        owner_qualname=declaring_owner.__qualname__,
                        member_name=member_name,
                    ),
                    owner=declaring_owner,
                    callable=member,
                    kind=definition.kind,
                ),
            )
    ordered = tuple(
        sorted(descriptors, key=lambda descriptor: descriptor.identity.key),
    )
    return AgentSignalHookCatalog(descriptors=ordered)


def _get_signal_hook_definition(
    function: FunctionType,
) -> AgentSignalHookDefinition | None:
    candidate = vars(function).get(AGENT_SIGNAL_HOOK_DEFINITION_KEY)
    if candidate is None:
        return None
    if not isinstance(candidate, AgentSignalHookDefinition):
        raise AgentDefinitionError("Agent signal hook metadata is invalid")
    return candidate


def _validate_hook_contract(function: FunctionType) -> None:
    if not isasyncgenfunction(function):
        raise AgentDefinitionError(
            "@on_signal method must be an async generator yielding AgentYield items"
        )
    hook_signature = signature(function)
    _validate_hook_parameters(function, hook_signature)
    _validate_hook_yield_type(function, hook_signature)


def _validate_hook_parameters(
    function: FunctionType,
    hook_signature: Signature,
) -> None:
    parameters = list(hook_signature.parameters.values())
    if not parameters or parameters[0].name != "self":
        raise AgentDefinitionError("@on_signal method must be an instance method")
    payload_parameters = parameters[1:]
    if len(payload_parameters) != 1:
        raise AgentDefinitionError(
            "@on_signal method must accept exactly one signal: AgentSignal argument"
        )
    parameter = payload_parameters[0]
    if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
        raise AgentDefinitionError("@on_signal method cannot use variable arguments")
    annotation = _resolve_signal_annotation(function, parameter)
    if annotation is not AgentSignal:
        raise AgentDefinitionError(
            "@on_signal method argument must be annotated AgentSignal"
        )


def _resolve_signal_annotation(
    function: FunctionType,
    parameter: Parameter,
) -> object:
    if parameter.annotation == Parameter.empty:
        raise AgentDefinitionError(
            "@on_signal method argument must be annotated AgentSignal"
        )
    return _resolve_type_hints(function).get(parameter.name, parameter.annotation)


def _validate_hook_yield_type(
    function: FunctionType,
    hook_signature: Signature,
) -> None:
    return_annotation = hook_signature.return_annotation
    if return_annotation == Signature.empty:
        raise AgentDefinitionError("@on_signal method return type is required")
    resolved = _resolve_type_hints(function).get("return", return_annotation)
    return_origin = get_origin(resolved)
    if return_origin is None and resolved is AsyncGenerator:
        raise AgentDefinitionError("@on_signal method yield type is required")
    if return_origin is not AsyncGenerator:
        raise AgentDefinitionError("@on_signal method must yield AgentYield items")
    return_args = get_args(resolved)
    if not return_args:
        raise AgentDefinitionError("@on_signal method yield type is required")
    yield_type = return_args[0]
    yield_origin = get_origin(yield_type)
    yield_candidate = yield_type if yield_origin is None else yield_origin
    if (
        not isinstance(yield_candidate, type)
        or yield_candidate.__module__ != "spakky.agent.yield_"
        or yield_candidate.__name__ != "AgentYield"
    ):
        raise AgentDefinitionError("@on_signal method must yield AgentYield items")


def _resolve_type_hints(function: FunctionType) -> dict[str, object]:
    try:
        return dict(get_type_hints(function, include_extras=True))
    except (NameError, TypeError) as e:
        raise AgentDefinitionError(
            "@on_signal method annotations cannot be resolved"
        ) from e
