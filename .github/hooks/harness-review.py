#!/usr/bin/env python3
"""Harness meta-review: token budget, duplicate detection, and AI compliance scaffold.

Architecture
------------
This script runs at sessionEnd (non-AI shell context) and does two things:

1. Automated structural checks — objective, deterministic:
   - Token budget per harness file
   - Duplicate prompt↔skill pairs

2. AI compliance evaluation scaffold — generates rich context for the AI agent
   that reads this report at sessionStart.  The script cannot holistically judge
   whether the code followed all harness rules (naming conventions, framework
   patterns, DDD shapes, AOP pairs, etc.) — only an AI can do that reliably.
   So instead it:
   - Maps each changed Python file to its applicable instruction files
   - Embeds a condensed git diff for those files
   - Lists quick automated signals (definitive rule violations detectable by regex)
   - Writes a structured evaluation prompt asking the AI to assess compliance
     against the FULL set of applicable harness rules
"""

import re
import subprocess
from pathlib import Path

GITHUB = Path(".github")
TOKEN_BUDGET = 900          # approx tokens (chars / 4) per harness file
DIFF_LINE_BUDGET = 200      # max diff lines to embed (avoid token bloat)
REPORT = GITHUB / "hooks" / "harness-review.md"

structural_issues: list[str] = []


# ── helpers ──────────────────────────────────────────────────────────────────

def approx_tokens(p: Path) -> int:
    return len(p.read_text("utf-8")) // 4


def get_session_changed_files() -> list[Path]:
    """Files changed in this session vs the base branch (existing files only)."""
    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        out = subprocess.run(
            ["git", "diff", "--name-only", base],
            capture_output=True, text=True, check=True,
        ).stdout
        return [Path(f) for f in out.splitlines() if Path(f).exists()]
    except Exception:
        return []


def get_session_diff(files: list[Path]) -> str:
    """Return a condensed unified diff for the given files, capped at DIFF_LINE_BUDGET lines."""
    if not files:
        return ""
    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        out = subprocess.run(
            ["git", "diff", base, "--", *[str(f) for f in files]],
            capture_output=True, text=True,
        ).stdout
        lines = out.splitlines()
        if len(lines) > DIFF_LINE_BUDGET:
            lines = lines[:DIFF_LINE_BUDGET] + [f"... [{len(lines) - DIFF_LINE_BUDGET} lines truncated]"]
        return "\n".join(lines)
    except Exception:
        return ""


def parse_instruction_files() -> list[tuple[str, str, Path]]:
    """Return [(apply_to_glob, name, path)] for all instruction files."""
    result = []
    for f in sorted((GITHUB / "instructions").glob("*.instructions.md")):
        text = f.read_text("utf-8")
        m = re.search(r'^applyTo:\s*["\']?([^"\'>\n]+)["\']?', text, re.MULTILINE)
        if m:
            name = f.stem.removesuffix(".instructions")
            result.append((m.group(1).strip(), name, f))
    return result


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Convert a glob pattern with ** support to a compiled regex."""
    # Tokenize to avoid mangling ** when replacing *
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob)
    result = []
    for part in parts:
        if part == "**/":
            result.append("(.*/)?")
        elif part == "**":
            result.append(".*")
        elif part == "*":
            result.append("[^/]*")
        elif part == "?":
            result.append("[^/]")
        else:
            result.append(re.escape(part))
    return re.compile("".join(result))


def map_files_to_instructions(
    files: list[Path],
    instructions: list[tuple[str, str, Path]],
) -> dict[Path, list[str]]:
    """Return {file: [instruction_name, ...]} for each changed file."""
    compiled = [(glob, name, _glob_to_regex(glob)) for glob, name, _ in instructions]
    mapping: dict[Path, list[str]] = {}
    for f in files:
        applicable = [
            name for glob, name, rx in compiled
            if re.fullmatch(rx, str(f)) or re.fullmatch(rx, f.name)
        ]
        if applicable:
            mapping[f] = applicable
    return mapping


# ── automated signals: definitive regex-detectable violations ─────────────────

_AUTO_SIGNALS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"#\s*type:\s*ignore"), "python-code §Type Safety", "`# type: ignore` is forbidden"),
    (re.compile(r"^class\s+Test\w*[:(]", re.MULTILINE), "test-writing §Structure", "class-based test (use functions)"),
]


def collect_auto_signals(files: list[Path]) -> list[str]:
    """Return definitive violation strings for files that match automated rules."""
    signals = []
    for py_file in files:
        if not py_file.suffix == ".py":
            continue
        try:
            content = py_file.read_text("utf-8")
        except Exception:
            continue
        for pattern, rule_ref, desc in _AUTO_SIGNALS:
            for m in pattern.finditer(content):
                lineno = content[: m.start()].count("\n") + 1
                signals.append(f"`{py_file}` line {lineno} — {desc} (**{rule_ref}**)")
    return signals


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


# ── 3. Build AI compliance evaluation scaffold ────────────────────────────────

changed_files = get_session_changed_files()
py_files = [f for f in changed_files if f.suffix == ".py"]

instructions = parse_instruction_files()
file_rule_map = map_files_to_instructions(py_files, instructions)
auto_signals = collect_auto_signals(py_files)

# Only include files that have applicable instructions in the diff
diff_candidates = [f for f in py_files if f in file_rule_map]
diff_text = get_session_diff(diff_candidates)


# ── 4. Write report ───────────────────────────────────────────────────────────

has_structural = bool(structural_issues)
has_py_changes = bool(file_rule_map)

if has_structural or has_py_changes or auto_signals:
    out: list[str] = ["# Harness Meta-Review Report\n\n"]

    # Structural issues (automated, deterministic)
    if has_structural:
        out.append("## Structural Issues\n\n")
        out += [f"- {i}\n" for i in structural_issues]
        out.append("\n_Resolve these to keep context-window usage efficient._\n\n")

    # AI compliance evaluation scaffold
    if has_py_changes or auto_signals:
        out.append("## AI Compliance Evaluation\n\n")
        out.append(
            "> **Action required (AI agent at sessionStart):** Evaluate the changed files "
            "below against all applicable harness rules. Provide a holistic qualitative "
            "assessment — consider naming, patterns, type safety, structure, DDD/AOP/plugin "
            "conventions, and anything else covered by the applicable instructions.\n\n"
        )

        # File → rules mapping table
        if file_rule_map:
            out.append("### Changed Files & Applicable Rules\n\n")
            out.append("| File | Applicable Instructions |\n")
            out.append("|------|--------------------------|\n")
            for f, rules in sorted(file_rule_map.items()):
                out.append(f"| `{f}` | {', '.join(f'`{r}`' for r in rules)} |\n")
            out.append("\n")

        # Automated signals (fast-path definitive violations)
        if auto_signals:
            out.append("### Automated Signals (definitive violations)\n\n")
            out += [f"- {s}\n" for s in auto_signals]
            out.append("\n_These are certain violations — fix regardless of AI assessment._\n\n")

        # Embedded diff
        if diff_text:
            out.append("### Session Diff (for AI review)\n\n")
            out.append("```diff\n")
            out.append(diff_text + "\n")
            out.append("```\n\n")

        # Evaluation prompt for the AI agent
        out.append("### Evaluation Prompt\n\n")
        out.append(
            "For each file in the table above, assess compliance with its listed instructions "
            "by reviewing the diff. For each file provide:\n\n"
            "1. **Grade**: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL\n"
            "2. **Observations**: Key compliance strengths and gaps (max 3 bullets)\n"
            "3. **Suggestions**: Specific improvements if PARTIAL or FAIL\n\n"
            "Then give an overall session compliance grade and a 1-sentence summary.\n"
        )

    REPORT.write_text("".join(out), "utf-8")
    total = len(structural_issues) + len(auto_signals)
    file_count = len(file_rule_map)
    print(
        f"[harness-review] report written — {total} automated issue(s),"
        f" {file_count} file(s) queued for AI evaluation — see {REPORT}"
    )
    for i in structural_issues:
        print(f"  [structural] {i}")
    for s in auto_signals:
        print(f"  [auto-signal] {s}")
else:
    REPORT.unlink(missing_ok=True)
    print("[harness-review] No issues found. No Python files with applicable harness rules changed.")

