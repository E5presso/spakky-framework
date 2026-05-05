"""Agent execution metadata contracts."""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import Parameter, Signature, getattr_static, isclass, signature
from types import NoneType
from typing import get_args, get_origin, get_type_hints

from spakky.agent.error import AgentDefinitionError
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.error import AbstractSpakkyPodError


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
class AgentExecutionSpec:
    """Declarative execution semantics that cannot be inferred from DI alone."""

    name: str | None = None
    objective: str | None = None
    accepted_signals: tuple[AgentSignalKind, ...] = ()
    recovery: RecoveryStrategy = RecoveryStrategy.NONE
    streaming_exposure_mode: StreamingExposureMode = StreamingExposureMode.BALANCED
    timeout_seconds: float | None = None
    limits: AgentExecutionLimits = field(default_factory=AgentExecutionLimits)
    delegation_allowed: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject execution specs that would fail later at bootstrap."""
        if self.name is not None and not self.name.strip():
            raise AgentDefinitionError("Agent name cannot be blank")
        if self.objective is not None and not self.objective.strip():
            raise AgentDefinitionError("Agent objective cannot be blank")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Agent timeout must be positive")
        if (
            self.timeout_seconds is not None
            and self.limits.timeout_seconds is not None
            and self.timeout_seconds != self.limits.timeout_seconds
        ):
            raise AgentDefinitionError("Agent timeout declarations must match")


@dataclass(eq=False)
class Agent(Pod):
    """UseCase-equivalent Pod stereotype for agentic workflow components."""

    spec: AgentExecutionSpec = field(default_factory=AgentExecutionSpec)

    def _initialize(self, obj: PodType) -> None:
        """Initialize Pod metadata and validate the Agent execute contract."""
        try:
            super()._initialize(obj)
        except AbstractSpakkyPodError as e:
            raise AgentDefinitionError("Agent Pod metadata is invalid") from e
        self._validate_execute_contract(obj)

    def validate_bootstrap(self) -> None:
        """Re-run definition validation during application bootstrap."""
        self._validate_execute_contract(self.target)

    def _validate_execute_contract(self, obj: PodType) -> None:
        if not isclass(obj):
            raise AgentDefinitionError("@Agent can only annotate classes")
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
