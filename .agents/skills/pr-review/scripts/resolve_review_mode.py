#!/usr/bin/env python3
"""Resolve a pr-review invocation without executing either review path."""

from __future__ import annotations

from collections.abc import Sequence
import json
import sys


MANUAL_VERDICTS = ("AUTO_APPROVE", "CHANGES_REQUESTED", "HUMAN_REVIEW")


class ReviewModeError(RuntimeError):
    """The pr-review invocation is ambiguous or malformed."""


def _pr_reference(value: str) -> str:
    if not value.strip() or value != value.strip() or value.startswith("--"):
        raise ReviewModeError("PR reference must be one nonblank argument")
    return value


def resolve_review_mode(arguments: Sequence[str]) -> dict[str, object]:
    """Return the exclusive manual-fresh or receipt-publication route."""

    tokens = list(arguments)
    process_state_positions = [
        index for index, token in enumerate(tokens) if token == "--process-state"
    ]
    if not process_state_positions:
        if len(tokens) > 1:
            raise ReviewModeError("manual pr-review accepts at most one PR reference")
        reference = _pr_reference(tokens[0]) if tokens else None
        return {
            "mode": "manual-fresh",
            "pr_reference": reference,
            "verdicts": list(MANUAL_VERDICTS),
        }
    if process_state_positions != [1] or len(tokens) != 3:
        raise ReviewModeError(
            "receipt publication requires: <PR> --process-state <PATH>"
        )
    reference = _pr_reference(tokens[0])
    process_state = tokens[2]
    if not process_state.strip() or process_state != process_state.strip():
        raise ReviewModeError("process state path must be one nonblank argument")
    return {
        "mode": "receipt-publication",
        "pr_reference": reference,
        "process_state": process_state,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """Print the deterministic invocation route as JSON."""

    raw_arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        route = resolve_review_mode(raw_arguments)
    except ReviewModeError as error:
        print(f"resolve-review-mode: {error}", file=sys.stderr)
        return 2
    print(json.dumps(route, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
