#!/usr/bin/env python3
"""Classify deterministic zero-file review categories from a Git diff path set."""

from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
import sys
import unicodedata


class ReviewPathError(RuntimeError):
    """The changed-path stream is not a canonical Git path set."""


def _canonical_path(raw_path: bytes) -> PurePosixPath:
    try:
        path = raw_path.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReviewPathError("changed paths must be valid UTF-8") from error
    if unicodedata.normalize("NFC", path) != path:
        raise ReviewPathError("changed paths must use NFC normalization")
    if not path or path.startswith("/") or "\\" in path:
        raise ReviewPathError("changed paths must be nonblank repo-relative paths")
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise ReviewPathError("changed paths must not contain control characters")

    relative = PurePosixPath(path)
    if relative.is_absolute() or relative.as_posix() != path:
        raise ReviewPathError("changed paths must use canonical POSIX syntax")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ReviewPathError("changed paths must not traverse the repository")
    return relative


def parse_null_paths(payload: bytes) -> tuple[PurePosixPath, ...]:
    """Parse the exact NUL-delimited output of ``git diff --name-only -z``."""

    if not payload:
        return ()
    if not payload.endswith(b"\0"):
        raise ReviewPathError("changed-path stream must end with NUL")
    raw_paths = payload[:-1].split(b"\0")
    if any(not raw_path for raw_path in raw_paths):
        raise ReviewPathError("changed-path stream contains an empty path")
    paths = tuple(_canonical_path(raw_path) for raw_path in raw_paths)
    if len(set(paths)) != len(paths):
        raise ReviewPathError("changed-path stream contains duplicate paths")
    return paths


def classify_review_paths(paths: tuple[PurePosixPath, ...]) -> dict[str, str]:
    """Return the conservative C08/C09 zero-match decision."""

    c08_matches = any(
        any(
            left == "adapters" and right == "apis"
            for left, right in zip(path.parts, path.parts[1:], strict=False)
        )
        for path in paths
    )
    c09_matches = any(
        any(
            part.casefold() == "models" or "repository" in part.casefold()
            for part in path.parts
        )
        for path in paths
    )
    return {
        "C08": "review" if c08_matches else "zero-match",
        "C09": "review" if c09_matches else "zero-match",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--null-stdin",
        action="store_true",
        required=True,
        help="read NUL-delimited changed paths from standard input",
    )
    return parser


def main() -> int:
    """Read, classify, and print a stable JSON decision."""

    _parser().parse_args()
    try:
        paths = parse_null_paths(sys.stdin.buffer.read())
        decision = classify_review_paths(paths)
    except ReviewPathError as error:
        print(f"review-paths-invalid: {error}", file=sys.stderr)
        return 2
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
