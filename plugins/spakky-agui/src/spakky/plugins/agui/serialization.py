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


def sse_frame_payload(frame: str) -> str:
    """Convert one AG-UI SSE frame into a raw JSON-line event payload."""
    payload_lines = [
        line.removeprefix("data:").lstrip()
        for line in frame.splitlines()
        if line.startswith("data:")
    ]
    return "\n".join(payload_lines) + "\n"
