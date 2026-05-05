"""Shared JSON-compatible type aliases for agent contracts."""

from collections.abc import Mapping, Sequence

type JsonPrimitive = bool | float | int | str | None
"""Scalar JSON value accepted by agent public contracts."""

type JsonValue = JsonPrimitive | Mapping[str, JsonValue] | Sequence[JsonValue]
"""Recursive JSON-compatible value used at model, signal, and evidence boundaries."""

type JsonObject = Mapping[str, JsonValue]
"""JSON object payload used by public agent contracts."""
