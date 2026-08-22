"""Tests for privacy-safe core Agent telemetry contracts."""

from math import inf, nan
from typing import cast

import pytest

import spakky.agent as public_api
from spakky.agent.error import AgentDefinitionError
from spakky.agent.telemetry import (
    AgentSpanKind,
    AgentSpanRecord,
    AgentSpanStatus,
    AgentTelemetryError,
    IAgentTelemetry,
)
from spakky.agent.types import JsonObject


def _record(**overrides: object) -> AgentSpanRecord:
    values: dict[str, object] = {
        "name": "agent.model",
        "kind": AgentSpanKind.MODEL,
        "started_at_ns": 10,
        "ended_at_ns": 20,
        "attributes": {"count": 1, "cached": False, "score": 0.5},
        "status": AgentSpanStatus.OK,
        "error_code": None,
    }
    values.update(overrides)
    return AgentSpanRecord(
        name=cast(str, values["name"]),
        kind=cast(AgentSpanKind, values["kind"]),
        started_at_ns=cast(int, values["started_at_ns"]),
        ended_at_ns=cast(int, values["ended_at_ns"]),
        attributes=cast(JsonObject, values["attributes"]),
        status=cast(AgentSpanStatus, values["status"]),
        error_code=cast(str | None, values["error_code"]),
    )


def test_agent_span_record_accepts_scalar_attributes_and_snapshots_them() -> None:
    """Completed span records cannot be changed through the caller's dictionary."""
    attributes: dict[str, object] = {"count": 1, "cached": False, "score": 0.5}
    record = _record(attributes=attributes)
    attributes["count"] = 9

    assert record.attributes == {"count": 1, "cached": False, "score": 0.5}


def test_agent_span_record_accepts_correlated_error_status() -> None:
    """An error record carries exactly one stable error code."""
    record = _record(
        status=AgentSpanStatus.ERROR,
        error_code="agent_model_execution_failed",
    )

    assert record.status is AgentSpanStatus.ERROR
    assert record.error_code == "agent_model_execution_failed"


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "model"},
        {"status": "ok"},
        {"name": ""},
        {"name": cast(str, 1)},
        {"started_at_ns": True},
        {"started_at_ns": cast(int, "10")},
        {"ended_at_ns": True},
        {"ended_at_ns": cast(int, "20")},
        {"started_at_ns": -1},
        {"started_at_ns": 21, "ended_at_ns": 20},
        {"status": AgentSpanStatus.ERROR},
        {"error_code": "unexpected"},
        {"status": AgentSpanStatus.ERROR, "error_code": ""},
        {"status": AgentSpanStatus.ERROR, "error_code": cast(str, 1)},
        {"attributes": {"": "value"}},
        {"attributes": {cast(str, 1): "value"}},
        {"attributes": {"nested": {"raw": "value"}}},
        {"attributes": {"score": inf}},
        {"attributes": {"score": nan}},
    ],
)
def test_agent_span_record_rejects_invalid_contracts(
    overrides: dict[str, object],
) -> None:
    """Malformed kinds, status, timestamps, errors, and attributes fail closed."""
    with pytest.raises(AgentDefinitionError):
        _record(**overrides)


def test_telemetry_public_exports_are_canonical() -> None:
    """Core observability ports and records are available from package root."""
    assert public_api.AgentSpanKind is AgentSpanKind
    assert public_api.AgentSpanRecord is AgentSpanRecord
    assert public_api.AgentSpanStatus is AgentSpanStatus
    assert public_api.AgentTelemetryError is AgentTelemetryError
    assert public_api.IAgentTelemetry is IAgentTelemetry
