"""Agent execution metadata contracts."""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import Parameter, Signature, getattr_static, isclass, signature
from types import NoneType
from typing import get_args, get_origin, get_type_hints
from urllib.parse import urlsplit

from spakky.agent.error import AgentDefinitionError
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


class AgentSignalKind(StrEnum):
    """Inbound stimulus kinds that an agent may accept while running."""

    USER_MESSAGE = "user_message"
    APPROVAL_DECISION = "approval_decision"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    STEERING_INSTRUCTION = "steering_instruction"
    EXTERNAL_EVENT = "external_event"
    SCHEDULER_WAKE_UP = "scheduler_wake_up"


@dataclass(frozen=True, slots=True)
class AgentExecutionLimits:
    """Bounded execution limits declared outside infrastructure capabilities."""

    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject limits that would fail later at bootstrap."""
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Agent timeout limit must be positive")


@dataclass(frozen=True, slots=True)
class AgentTeammate:
    """Declared collaborator an agent may delegate to during execution.

    A teammate is resolved either in-process by a local @Agent Pod type or
    remotely by an AgentCard endpoint URL. Exactly one binding is declared;
    the runtime delegation wiring (follow-up E4) consumes this declaration.
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


class CompactionStrategy(StrEnum):
    """Ordered context-compaction tactic applied when the threshold trips."""

    DROP_OLDEST_EVIDENCE = "drop_oldest_evidence"
    SUMMARIZE_TRANSCRIPT = "summarize_transcript"
    DEDUPLICATE_EVIDENCE = "deduplicate_evidence"
    OFFLOAD_TO_EXTERNAL_STORE = "offload_to_external_store"


@dataclass(frozen=True, slots=True)
class AgentCompactionPolicy:
    """Declared compaction chain plus the token threshold that triggers it.

    The strategies form an ordered chain applied in sequence once the
    running token count crosses ``trigger_token_threshold``. The runtime
    compaction handler (follow-up C7) consumes this declaration.
    """

    strategies: tuple[CompactionStrategy, ...]
    trigger_token_threshold: int

    def __post_init__(self) -> None:
        """Reject compaction policies that cannot be enforced consistently."""
        if not self.strategies:
            raise AgentDefinitionError(
                "Agent compaction policy requires at least one strategy"
            )
        if len(set(self.strategies)) != len(self.strategies):
            raise AgentDefinitionError(
                "Agent compaction strategies cannot repeat in the chain"
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
    timeout_seconds: float | None = None
    limits: AgentExecutionLimits = field(default_factory=AgentExecutionLimits)
    teammates: tuple[AgentTeammate, ...] = ()
    compaction: AgentCompactionPolicy | None = None
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
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Agent timeout must be positive")
        if (
            self.timeout_seconds is not None
            and self.limits.timeout_seconds is not None
            and self.timeout_seconds != self.limits.timeout_seconds
        ):
            raise AgentDefinitionError("Agent timeout declarations must match")
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

    def _initialize(self, obj: PodType) -> None:
        """Initialize Pod metadata and validate the Agent execute contract."""
        agent_class = self._ensure_agent_class(obj)
        try:
            super()._initialize(agent_class)
        except AbstractSpakkyPodError as e:
            raise AgentDefinitionError("Agent Pod metadata is invalid") from e
        self._validate_execute_contract(agent_class)
        self.tool_catalog = discover_agent_tools(agent_class)

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

    def _validate_execute_contract(self, obj: type[object]) -> None:
        execute = getattr_static(obj, "execute", None)
        if execute is None:
            raise AgentDefinitionError("@Agent class must define execute()")
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
