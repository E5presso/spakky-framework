"""Shared JSON serialization for AG-UI adapter frames.

The projector serializes tool results and run output, and HITL serializes
approval args — both need the same neutral ``JsonValue`` -> JSON-text encoding,
so it lives at module scope rather than being inlined twice.
"""

from json import dumps

from spakky.agent.types import JsonValue


def dump_json(value: JsonValue) -> str:
    """Serialize a neutral JSON value to compact JSON text."""
    return dumps(value, separators=(",", ":"), ensure_ascii=False)
