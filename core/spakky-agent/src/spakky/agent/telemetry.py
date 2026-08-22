"""Privacy-safe telemetry records emitted by the standard Agent runtime."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from types import MappingProxyType

from spakky.agent.error import AbstractSpakkyAgentError, AgentDefinitionError
from spakky.agent.types import JsonObject


class AgentSpanKind(StrEnum):
    """Stable operation families emitted by AgentRunner."""

    RUN = "run"
    MODEL = "model"
    TOOL = "tool"
    RETRIEVAL = "retrieval"


class AgentSpanStatus(StrEnum):
    """Terminal status of one completed operation record."""

    OK = "ok"
    ERROR = "error"


class AgentTelemetryError(AbstractSpakkyAgentError):
    """Raised when an injected telemetry adapter cannot record a span."""

    message = "Agent telemetry recording failed"


@dataclass(frozen=True, slots=True)
class AgentSpanRecord:
    """Completed span data containing scalar metadata but no prompt payloads."""

    name: str
    kind: AgentSpanKind
    started_at_ns: int
    ended_at_ns: int
    attributes: JsonObject = field(default_factory=dict)
    status: AgentSpanStatus = AgentSpanStatus.OK
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AgentSpanKind):
            raise AgentDefinitionError("Agent telemetry span kind is invalid")
        if not isinstance(self.status, AgentSpanStatus):
            raise AgentDefinitionError("Agent telemetry span status is invalid")
        if not isinstance(self.name, str) or not self.name.strip():
            raise AgentDefinitionError("Agent telemetry span name cannot be blank")
        if (
            isinstance(self.started_at_ns, bool)
            or not isinstance(self.started_at_ns, int)
            or isinstance(self.ended_at_ns, bool)
            or not isinstance(self.ended_at_ns, int)
            or self.started_at_ns < 0
            or self.ended_at_ns < self.started_at_ns
        ):
            raise AgentDefinitionError("Agent telemetry span timestamps are invalid")
        if (self.status is AgentSpanStatus.ERROR) != (self.error_code is not None):
            raise AgentDefinitionError(
                "Agent telemetry error status requires exactly one error code"
            )
        if self.error_code is not None and (
            not isinstance(self.error_code, str) or not self.error_code.strip()
        ):
            raise AgentDefinitionError("Agent telemetry error code cannot be blank")
        for key, value in self.attributes.items():
            if not isinstance(key, str) or not key.strip():
                raise AgentDefinitionError(
                    "Agent telemetry attribute key cannot be blank"
                )
            if not isinstance(value, str | bool | int | float):
                raise AgentDefinitionError(
                    "Agent telemetry attributes must contain scalar values"
                )
            if isinstance(value, float) and not isfinite(value):
                raise AgentDefinitionError(
                    "Agent telemetry numeric attributes must be finite"
                )
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(self.attributes)),
        )


class IAgentTelemetry(ABC):
    """Optional outbound port receiving completed privacy-safe Agent spans."""

    @abstractmethod
    def record(self, span: AgentSpanRecord) -> None:
        """Record one completed span without changing Agent execution."""
        ...
