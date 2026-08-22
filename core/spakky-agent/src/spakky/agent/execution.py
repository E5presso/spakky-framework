"""Agent execution metadata contracts."""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import Parameter, Signature, getattr_static, isclass, signature
from types import NoneType
from typing import get_args, get_origin, get_type_hints
from urllib.parse import urlsplit

from spakky.agent.compaction import ICompactionStrategy
from spakky.agent.delegation import build_teammate_tool_descriptors
from spakky.agent.error import AgentDefinitionError
from spakky.agent.hooks import AgentSignalHookCatalog, discover_agent_signal_hooks
from spakky.agent.signal import AgentSignalKind
from spakky.agent.structured_output import _structured_output_contract
from spakky.agent.tooling import AgentToolCatalog, discover_agent_tools
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.error import AbstractSpakkyPodError

REMOTE_AGENT_CARD_SCHEMES = ("http", "https")
"""URL schemes accepted for a remote teammate's AgentCard endpoint."""


class RecoveryStrategy(StrEnum):
    """Recovery strategy requested by an agent execution contract."""

    NONE = "none"
    ACTION_BOUNDARY = "action_boundary"


class StreamingExposureMode(StrEnum):
    """Streaming output guard profile exposed by agent execution."""

    LOW_LATENCY = "low_latency"
    BALANCED = "balanced"
    STRICT = "strict"
    NO_STREAM_UNTIL_FINAL_GUARDED = "no_stream_until_final_guarded"


@dataclass(frozen=True, slots=True)
class AgentExecutionLimits:
    """Bounded execution limits declared outside infrastructure capabilities."""

    max_steps: int = 8
    max_tool_calls: int = 32
    max_tokens: int | None = None
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject limits that would fail later at bootstrap."""
        if self.max_steps <= 0:
            raise AgentDefinitionError("Agent model-step limit must be positive")
        if self.max_tool_calls <= 0:
            raise AgentDefinitionError("Agent tool-call limit must be positive")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise AgentDefinitionError("Agent token limit must be positive")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Agent timeout limit must be positive")


@dataclass(frozen=True, slots=True)
class AgentTeammate:
    """Declared collaborator an agent may delegate to during execution.

    A teammate is resolved either in-process by a local @Agent Pod type or
    remotely by an AgentCard endpoint URL. Exactly one binding is declared; the
    runtime exposes it as a synthetic teammate delegation tool and dispatches it
    through the local runner or an injected ``IAgentDelegate`` port.
    """

    name: str
    pod: type[object] | None = None
    card_url: str | None = None

    def __post_init__(self) -> None:
        """Reject teammates that cannot resolve to a single delegate target."""
        if not self.name.strip():
            raise AgentDefinitionError("Agent teammate name cannot be blank")
        if (self.pod is None) == (self.card_url is None):
            raise AgentDefinitionError(
                "Agent teammate must declare exactly one of a local pod "
                "or a remote AgentCard url"
            )
        if self.pod is not None and not isclass(self.pod):
            raise AgentDefinitionError("Agent teammate pod must be a class")
        if self.card_url is not None:
            parts = urlsplit(self.card_url)
            if parts.scheme not in REMOTE_AGENT_CARD_SCHEMES or not parts.netloc:
                raise AgentDefinitionError(
                    "Agent teammate AgentCard url must be an http(s) endpoint"
                )


@dataclass(frozen=True, slots=True)
class AgentCompactionPolicy:
    """Declared compaction chain plus the token threshold that triggers it.

    The strategies form an ordered chain of pluggable ``ICompactionStrategy``
    ports applied in sequence once the running token estimate crosses
    ``trigger_token_threshold``. The runner threads each strategy's output into
    the next, so chain order is the compaction order (ADR-0013 §7).
    """

    strategies: tuple[ICompactionStrategy, ...]
    trigger_token_threshold: int

    def __post_init__(self) -> None:
        """Reject compaction policies that cannot be enforced consistently."""
        if not self.strategies:
            raise AgentDefinitionError(
                "Agent compaction policy requires at least one strategy"
            )
        if self.trigger_token_threshold <= 0:
            raise AgentDefinitionError(
                "Agent compaction trigger token threshold must be positive"
            )


@dataclass(frozen=True, slots=True)
class AgentExecutionSpec:
    """Declarative execution semantics that cannot be inferred from DI alone."""

    name: str | None = None
    objective: str | None = None
    instructions: str | None = None
    output_type: type[object] | None = None
    accepted_signals: tuple[AgentSignalKind, ...] = ()
    recovery: RecoveryStrategy = RecoveryStrategy.NONE
    streaming_exposure_mode: StreamingExposureMode = StreamingExposureMode.BALANCED
    limits: AgentExecutionLimits = field(default_factory=AgentExecutionLimits)
    teammates: tuple[AgentTeammate, ...] = ()
    compaction: AgentCompactionPolicy | None = None
    refresh_context_each_step: bool = False
    delegation_allowed: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject execution specs that would fail later at bootstrap."""
        if self.name is not None and not self.name.strip():
            raise AgentDefinitionError("Agent name cannot be blank")
        if self.objective is not None and not self.objective.strip():
            raise AgentDefinitionError("Agent objective cannot be blank")
        if self.instructions is not None and not self.instructions.strip():
            raise AgentDefinitionError("Agent instructions cannot be blank")
        if self.output_type is not None and not isclass(self.output_type):
            raise AgentDefinitionError("Agent output type must be a class")
        if self.output_type is not None:
            _structured_output_contract(self.output_type)
        teammate_names = [teammate.name for teammate in self.teammates]
        if len(set(teammate_names)) != len(teammate_names):
            raise AgentDefinitionError("Agent teammate names must be unique")


@dataclass(eq=False)
class Agent(Pod):
    """UseCase-equivalent Pod stereotype for agentic workflow components."""

    spec: AgentExecutionSpec = field(default_factory=AgentExecutionSpec)
    tool_catalog: AgentToolCatalog = field(
        init=False,
        default_factory=AgentToolCatalog,
    )
    signal_hook_catalog: AgentSignalHookCatalog = field(
        init=False,
        default_factory=AgentSignalHookCatalog,
    )

    def _initialize(self, obj: PodType) -> None:
        """Initialize Pod metadata and validate the Agent execute contract."""
        agent_class = self._ensure_agent_class(obj)
        try:
            super()._initialize(agent_class)
        except AbstractSpakkyPodError as e:
            raise AgentDefinitionError("Agent Pod metadata is invalid") from e
        self._ensure_execute_provided(agent_class)
        self._validate_execute_contract(agent_class)
        discovered_tools = discover_agent_tools(agent_class)
        teammate_tools = build_teammate_tool_descriptors(
            agent_class,
            self.spec.teammates,
        )
        self.tool_catalog = AgentToolCatalog(
            descriptors=(*discovered_tools.descriptors, *teammate_tools),
        )
        self.signal_hook_catalog = discover_agent_signal_hooks(agent_class)

    def validate_bootstrap(self) -> None:
        """Re-run definition validation during application bootstrap."""
        self._validate_execute_contract(self._ensure_agent_class(self.target))

    def required_persistence_repository_types(self) -> tuple[type[object], ...]:
        """Return repository ports required by this Agent's durable path."""
        from spakky.agent.interfaces.repository import (
            IAgentEvidenceRepository,
            IAgentSignalRepository,
            IAgentStateRepository,
        )

        if (
            self.spec.recovery is RecoveryStrategy.ACTION_BOUNDARY
            or len(self.spec.accepted_signals) > 0
        ):
            return (
                IAgentStateRepository,
                IAgentSignalRepository,
                IAgentEvidenceRepository,
            )
        return ()

    def _ensure_agent_class(self, obj: PodType) -> type[object]:
        if not isinstance(obj, type):
            raise AgentDefinitionError("@Agent can only annotate classes")
        return obj

    def _ensure_execute_provided(self, obj: type[object]) -> None:
        """Bind the framework-owned loop as ``execute()`` when none is declared.

        ADR-0013 §1 keeps the ``execute()`` interface but lets the framework
        runner auto-provide the standard loop. A developer who declares only a
        spec plus ``@agent_tool`` methods writes no loop body; the synthesized
        ``execute()`` satisfies the strict contract validated below, so the
        validator is reused rather than weakened. A developer-written
        ``execute()`` is left untouched for custom control.
        """
        if getattr_static(obj, "execute", None) is not None:
            return
        from spakky.agent.runner import runner_backed_execute

        # Framework metaprogramming: bind the runner-backed generator as the
        # agent's execute() so the strict contract validation accepts it.
        obj.execute = runner_backed_execute  # type: ignore[attr-defined] - synthesized contract method

    def _validate_execute_contract(self, obj: type[object]) -> None:
        # _ensure_execute_provided guarantees execute() exists before validation.
        execute = getattr_static(obj, "execute")
        execute_signature = signature(execute)
        self._validate_execute_parameters(execute_signature)
        return_annotation = self._resolve_execute_return_annotation(
            execute,
            execute_signature,
        )
        self._validate_execute_return_type(return_annotation)

    def _validate_execute_parameters(self, execute_signature: Signature) -> None:
        parameters = list(execute_signature.parameters.values())
        if not parameters or parameters[0].name != "self":
            raise AgentDefinitionError("@Agent.execute() must be an instance method")
        for parameter in parameters[1:]:
            if parameter.kind == Parameter.POSITIONAL_ONLY:
                raise AgentDefinitionError(
                    "@Agent.execute() cannot use positional-only parameters"
                )
            if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                raise AgentDefinitionError(
                    "@Agent.execute() cannot use variable arguments"
                )
            if parameter.annotation == Parameter.empty:
                raise AgentDefinitionError(
                    "@Agent.execute() parameters must be type annotated"
                )

    def _resolve_execute_return_annotation(
        self,
        execute: object,
        execute_signature: Signature,
    ) -> object:
        return_annotation = execute_signature.return_annotation
        if return_annotation == Signature.empty:
            return return_annotation
        hint_target = (
            execute.__func__
            if isinstance(execute, (staticmethod, classmethod))
            else execute
        )
        try:
            type_hints = get_type_hints(hint_target, include_extras=True)
        except (NameError, TypeError) as e:
            raise AgentDefinitionError(
                "@Agent.execute() return type annotation cannot be resolved"
            ) from e
        return type_hints.get("return", return_annotation)

    def _validate_execute_return_type(self, return_annotation: object) -> None:
        if return_annotation == Signature.empty:
            raise AgentDefinitionError("@Agent.execute() return type is required")
        return_origin = get_origin(return_annotation)
        if return_origin is None and return_annotation in (AsyncGenerator, Generator):
            return_origin = return_annotation
        if return_origin not in (AsyncGenerator, Generator):
            return
        return_args = get_args(return_annotation)
        if not return_args:
            raise AgentDefinitionError("@Agent.execute() yield type is required")
        yield_type = return_args[0]
        yield_origin = get_origin(yield_type)
        yield_candidate = yield_type if yield_origin is None else yield_origin
        if (
            not isclass(yield_candidate)
            or yield_candidate.__module__ != "spakky.agent.yield_"
            or yield_candidate.__name__ != "AgentYield"
        ):
            raise AgentDefinitionError("@Agent.execute() must yield AgentYield items")
        self._validate_generator_control_types(return_origin, return_args)

    def _validate_generator_control_types(
        self,
        return_origin: object,
        return_args: tuple[object, ...],
    ) -> None:
        if len(return_args) < 2 or not self._is_none_annotation(return_args[1]):
            raise AgentDefinitionError(
                "@Agent.execute() generator send type must be None"
            )
        if (
            return_origin is Generator
            and len(return_args) >= 3
            and not self._is_none_annotation(return_args[2])
        ):
            raise AgentDefinitionError(
                "@Agent.execute() sync generator return type must be None"
            )

    def _is_none_annotation(self, annotation: object) -> bool:
        return annotation is None or annotation is NoneType
