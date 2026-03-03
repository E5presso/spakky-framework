#!/usr/bin/env python3
"""Harness meta-review: token budget, duplicate detection, and session compliance check."""

import re
import subprocess
from pathlib import Path

GITHUB = Path(".github")
TOKEN_BUDGET = 900  # approx tokens (chars / 4) per file
REPORT = GITHUB / "hooks" / "harness-review.md"

structural_issues: list[str] = []
compliance_violations: list[tuple[str, str]] = []  # (file_location, rule_ref)


# ── helpers ──────────────────────────────────────────────────────────────────

def approx_tokens(p: Path) -> int:
    return len(p.read_text("utf-8")) // 4


def get_session_python_files() -> list[Path]:
    """Python files changed in this session vs the base branch."""
    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        out = subprocess.run(
            ["git", "diff", "--name-only", base],
            capture_output=True, text=True, check=True,
        ).stdout
        return [
            Path(f) for f in out.splitlines()
            if f.endswith(".py") and Path(f).exists()
        ]
    except Exception:
        return []


# ── 1. Token budget check ─────────────────────────────────────────────────────

for pattern in [
    "instructions/*.instructions.md",
    "prompts/*.prompt.md",
    "skills/*/SKILL.md",
]:
    for f in sorted(GITHUB.glob(pattern)):
        t = approx_tokens(f)
        if t > TOKEN_BUDGET:
            rel = str(f.relative_to(GITHUB))
            structural_issues.append(
                f"**{rel}**: ~{t} tokens (budget: {TOKEN_BUDGET}) — trim or split"
            )


# ── 2. Duplicate prompt↔skill detection ───────────────────────────────────────

PROMPT_DIR = GITHUB / "prompts"
SKILL_DIR = GITHUB / "skills"

if PROMPT_DIR.exists() and SKILL_DIR.exists():
    prompt_stems = {
        f.stem.removesuffix(".prompt"): f for f in PROMPT_DIR.glob("*.prompt.md")
    }
    skill_dirs = {d.name: d for d in SKILL_DIR.iterdir() if d.is_dir()}

    # Known alias pairs (prompt-name → skill-folder-name)
    for pname, sname in [
        ("coverage", "improve-coverage"),
        ("plugin", "create-plugin"),
        ("review", "review-pr"),
    ]:
        if pname in prompt_stems and sname in skill_dirs:
            structural_issues.append(
                f"**prompts/{pname}.prompt.md** duplicates **skills/{sname}/SKILL.md**"
                " — remove prompt, keep skill"
            )

    for pname in prompt_stems:
        if pname in skill_dirs:
            structural_issues.append(
                f"**prompts/{pname}.prompt.md** duplicates **skills/{pname}/SKILL.md**"
                " — remove prompt, keep skill"
            )


# ── 3. Qualitative compliance check on session-changed Python files ───────────

# Each entry: (compiled pattern, multiline, rule ref, short description)
REGEX_RULES = [
    (
        re.compile(r"#\s*type:\s*ignore"),
        False,
        "python-code §Type Safety",
        "`# type: ignore` is forbidden",
    ),
    (
        re.compile(r"^class\s+Test\w*\s*[:(]", re.MULTILINE),
        True,
        "test-writing §Structure",
        "class-based test is forbidden — use functions",
    ),
    (
        re.compile(r"\bAny\b"),
        False,
        "python-code §Type Safety",
        "`Any` used without inline justification comment",
    ),
]


def _has_inline_justification(content: str, match_start: int) -> bool:
    """Return True if the line containing match_start has an inline `# noqa` or `# type:` comment."""
    line_start = content.rfind("\n", 0, match_start) + 1
    line_end_nl = content.find("\n", match_start)
    line = content[line_start: line_end_nl if line_end_nl != -1 else len(content)]
    return bool(re.search(r"#\s*(noqa|type:|ANN4)", line))


def check_test_docstrings(path: Path, lines: list[str]) -> list[tuple[str, str]]:
    """Return violations for test functions missing an immediate docstring."""
    if "/tests/" not in str(path) and not str(path).startswith("tests/"):
        return []
    results = []
    for i, line in enumerate(lines):
        if re.match(r"\s*def test_", line):
            for j in range(i + 1, min(i + 6, len(lines))):
                stripped = lines[j].strip()
                if stripped:
                    if not (stripped.startswith('"""') or stripped.startswith("'''")):
                        results.append((
                            f"`{path}` line {i + 1}: test function missing docstring",
                            "test-writing §Structure",
                        ))
                    break
    return results


changed_files = get_session_python_files()
files_with_violations: set[str] = set()

for py_file in changed_files:
    try:
        content = py_file.read_text("utf-8")
        lines = content.splitlines()
    except Exception:
        continue

    file_key = str(py_file)

    for pattern, _multiline, rule_ref, desc in REGEX_RULES:
        for m in pattern.finditer(content):
            # Skip Any if it has inline justification
            if "Any" in desc and _has_inline_justification(content, m.start()):
                continue
            lineno = content[: m.start()].count("\n") + 1
            compliance_violations.append((
                f"`{py_file}` line {lineno}: {desc} — **{rule_ref}**",
                rule_ref,
            ))
            files_with_violations.add(file_key)

    for loc, rule_ref in check_test_docstrings(py_file, lines):
        compliance_violations.append((loc + f" — **{rule_ref}**", rule_ref))
        files_with_violations.add(file_key)

# Compliance rate: fraction of changed files with zero violations
total_files = len(changed_files)
clean_files = total_files - len(files_with_violations)
compliance_pct = round(100 * clean_files / total_files) if total_files else 100

if compliance_pct >= 90:
    grade = "✅ PASS"
elif compliance_pct >= 70:
    grade = "⚠️ PARTIAL"
else:
    grade = "❌ FAIL"


# ── 4. Write report ───────────────────────────────────────────────────────────

has_anything = structural_issues or compliance_violations

if has_anything:
    lines_out: list[str] = ["# Harness Meta-Review Report\n\n"]

    if structural_issues:
        lines_out.append("## Structural Issues\n\n")
        lines_out += [f"- {i}\n" for i in structural_issues]
        lines_out.append("\n_Resolve these to keep context-window usage efficient._\n\n")

    lines_out.append("## Session Compliance\n\n")
    lines_out.append(
        f"**{grade}** — {compliance_pct}% compliant"
        f" ({clean_files}/{total_files} changed files violation-free)\n\n"
    )
    if compliance_violations:
        lines_out.append("### Violations\n\n")
        lines_out += [f"- {v}\n" for v, _ in compliance_violations]
        lines_out.append(
            "\n_Each violation indicates a harness rule was not followed."
            " Fix before merging._\n"
        )
    else:
        lines_out.append("_No rule violations found in changed files._\n")

    REPORT.write_text("".join(lines_out), "utf-8")
    total = len(structural_issues) + len(compliance_violations)
    print(f"[harness-review] {total} issue(s) — compliance {compliance_pct}% — see {REPORT}")
    for i in structural_issues:
        print(f"  [structural] {i}")
    for v, _ in compliance_violations:
        print(f"  [compliance] {v}")
else:
    REPORT.unlink(missing_ok=True)
    print(f"[harness-review] No issues found. Compliance: {compliance_pct}% ({total_files} files checked).")

