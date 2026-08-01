"""Exercise the canonical terminal-return issue validator in both consumers."""

from pathlib import Path
import re
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
VALIDATOR_PATHS = (
    REPOSITORY_ROOT / ".agents/skills/process-ticket/SKILL.md",
    REPOSITORY_ROOT / ".agents/skills/autopilot/phases/phase-3-wave-loop.md",
)
CANONICAL_FIXTURES = (
    "issue: #1",
    "issue: #42",
    "issue: #123456",
)
NON_CANONICAL_FIXTURES = (
    "issue: ABC-42",
    "issue: 42",
    "issue: #42x",
    "issue: #-42",
)


def extract_issue_validator(path: Path) -> str:
    validators = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("^issue: ")
    ]
    if len(validators) != 1:
        raise ValueError(
            f"{path}: expected exactly one issue validator, found {len(validators)}"
        )
    return validators[0]


def main() -> int:
    failures: list[str] = []
    validators = {path: extract_issue_validator(path) for path in VALIDATOR_PATHS}

    if len(set(validators.values())) != 1:
        failures.append("process-ticket and autopilot issue validators differ")

    for path, validator in validators.items():
        compiled = re.compile(validator)
        for fixture in CANONICAL_FIXTURES:
            if compiled.fullmatch(fixture) is None:
                failures.append(f"{path}: rejected canonical fixture {fixture!r}")
        for fixture in NON_CANONICAL_FIXTURES:
            if compiled.fullmatch(fixture) is not None:
                failures.append(f"{path}: accepted non-canonical fixture {fixture!r}")

    if failures:
        print("terminal-return issue contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("terminal-return issue contract checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
