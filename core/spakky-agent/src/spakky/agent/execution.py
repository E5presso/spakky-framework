"""Agent execution metadata contracts."""

from dataclasses import dataclass, field
from enum import StrEnum

from spakky.agent.error import AgentDefinitionError


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
class AgentExecutionSpec:
    """Declarative execution semantics that cannot be inferred from DI alone."""

    accepted_signals: tuple[AgentSignalKind, ...] = ()
    recovery: RecoveryStrategy = RecoveryStrategy.NONE
    streaming_exposure_mode: StreamingExposureMode = StreamingExposureMode.BALANCED
    timeout_seconds: float | None = None
    delegation_allowed: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject execution specs that would fail later at bootstrap."""
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise AgentDefinitionError("Agent timeout must be positive")


@dataclass(frozen=True, slots=True)
class Agent:
    """Public agent definition metadata exported by the core package."""

    spec: AgentExecutionSpec = field(default_factory=AgentExecutionSpec)
