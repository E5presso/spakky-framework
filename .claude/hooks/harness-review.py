#!/usr/bin/env python3
"""Harness meta-review: token budget, duplicate detection, and AI compliance scaffold.

Architecture
------------
This script runs at sessionEnd (non-AI shell context). It performs automated
structural checks and prepares a rich evaluation scaffold for the AI agent.

The AI-driven qualitative evaluation is performed by the agent itself via the
`harness-review` skill, which the agent invokes as the FINAL step of every
coding session (mandated by the agent spec). The skill reads this script's
output and performs holistic qualitative assessment of all session changes
against applicable harness rules.

Responsibilities of this script (automated, deterministic):
1. Token budget per harness file — flags files exceeding 900-token budget
2. Token efficiency metrics — always-loaded total, per-file tok/rule density
3. Duplicate prompt↔skill pairs — same workflow defined in both directories
4. AI compliance evaluation scaffold for source code — for changed Python files:
    - Maps each file to its applicable instruction files (via applyTo: globs)
    - Embeds a condensed git diff for those files
    - Lists automated signals (definitive rule violations detectable by regex)
    - Writes a structured evaluation prompt for the AI skill to assess compliance
5. AI evaluation scaffold for harness-file changes:
    - Lists which harness files changed this session
    - Embeds their diffs for AI review
    - Writes a quality evaluation prompt (clarity, token efficiency, coverage, structure)

All findings are written to harness-review.md and consumed by the
`harness-review` skill when the agent invokes it.

Usage
-----
    # Review changes vs base branch (default behavior)
    python harness-review.py

    # Review only uncommitted changes (worktree)
    python harness-review.py --scope worktree

    # Session-based workflow:
    python harness-review.py start   # Mark session start (saves current HEAD)
    # ... do work ...
    python harness-review.py --scope session  # Review only session changes
    python harness-review.py end     # Clear session marker
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

CLAUDE_DIR = Path(".claude")
TOKEN_BUDGET = 900  # approx tokens (chars / 4) per harness file
DIFF_LINE_BUDGET = 200  # max diff lines to embed (avoid token bloat)
REPORT = CLAUDE_DIR / "hooks" / "harness-review.md"
SESSION_MARKER = CLAUDE_DIR / "hooks" / ".session-start"

Scope = Literal["branch", "worktree", "session"]

structural_issues: list[str] = []


# ── helpers ──────────────────────────────────────────────────────────────────


def approx_tokens(p: Path) -> int:
    return len(p.read_text("utf-8")) // 4


def _find_base_ref() -> str:
    """Return the merge-base SHA for comparison, trying several candidates."""
    candidates = ["origin/HEAD", "origin/develop", "origin/main", "origin/master"]
    for ref in candidates:
        result = subprocess.run(
            ["git", "merge-base", "HEAD", ref],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    # Last resort: first commit reachable from HEAD that is NOT in current branch
    result = subprocess.run(
        ["git", "log", "--oneline", "--first-parent", "HEAD"],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.strip().splitlines()
    if len(lines) > 1:
        return lines[-1].split()[0]  # oldest commit SHA
    return ""


def _get_ref_for_scope(scope: Scope) -> str:
    """Return the git ref to diff against based on scope."""
    if scope == "worktree":
        return "HEAD"
    if scope == "session":
        if SESSION_MARKER.exists():
            return SESSION_MARKER.read_text("utf-8").strip()
        # Fallback to HEAD if no session marker (shows uncommitted only)
        return "HEAD"
    # scope == "branch"
    return _find_base_ref()


def start_session() -> None:
    """Mark the start of a coding session by saving current HEAD SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("[harness-review] ERROR: Failed to get current HEAD SHA")
        sys.exit(1)
    sha = result.stdout.strip()
    SESSION_MARKER.write_text(sha, "utf-8")
    print(f"[harness-review] Session started at {sha[:8]}")


def end_session() -> None:
    """Clear the session marker."""
    if SESSION_MARKER.exists():
        SESSION_MARKER.unlink()
        print("[harness-review] Session marker cleared")
    else:
        print("[harness-review] No active session marker found")


def get_session_changed_files(scope: Scope) -> list[Path]:
    """Files changed based on scope (existing files only)."""
    try:
        base = _get_ref_for_scope(scope)
        if not base:
            return []
        out = subprocess.run(
            ["git", "diff", "--name-only", base],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [Path(f) for f in out.splitlines() if Path(f).exists()]
    except Exception:
        return []


def get_session_diff(files: list[Path], scope: Scope) -> str:
    """Return a condensed unified diff for the given files, capped at DIFF_LINE_BUDGET lines."""
    if not files:
        return ""
    try:
        base = _get_ref_for_scope(scope)
        if not base:
            return ""
        out = subprocess.run(
            ["git", "diff", base, "--", *[str(f) for f in files]],
            capture_output=True,
            text=True,
        ).stdout
        lines = out.splitlines()
        if len(lines) > DIFF_LINE_BUDGET:
            lines = lines[:DIFF_LINE_BUDGET] + [
                f"... [{len(lines) - DIFF_LINE_BUDGET} lines truncated]"
            ]
        return "\n".join(lines)
    except Exception:
        return ""


def parse_instruction_files() -> list[tuple[str, str, Path]]:
    """Return [(apply_to_glob, name, path)] for all rule files in .claude/rules/."""
    result = []
    rules_dir = CLAUDE_DIR / "rules"
    if not rules_dir.exists():
        return result
    for f in sorted(rules_dir.rglob("*.md")):
        text = f.read_text("utf-8")
        # Parse paths from YAML frontmatter: paths:\n  - "glob"
        paths_matches = re.findall(
            r'^\s*-\s*["\']?([^"\'>\n]+)["\']?\s*$', text, re.MULTILINE
        )
        # Only consider paths within the frontmatter block
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            paths_matches = re.findall(
                r'^\s*-\s*["\']?([^"\'>\n]+)["\']?\s*$', fm_text, re.MULTILINE
            )
        name = f.stem
        for glob_pattern in paths_matches:
            result.append((glob_pattern.strip(), name, f))
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
            name
            for glob, name, rx in compiled
            if re.fullmatch(rx, str(f)) or re.fullmatch(rx, f.name)
        ]
        if applicable:
            mapping[f] = applicable
    return mapping


# ── automated signals: definitive regex-detectable violations ─────────────────

_AUTO_SIGNALS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"#\s*type:\s*ignore(?!\[)"),
        "python-code §옵트아웃 주석",
        "`# type: ignore` without error code (require `# type: ignore[code] - reason`)",
    ),
    (
        re.compile(r"^class\s+Test\w*[:(]", re.MULTILINE),
        "test-writing §Structure",
        "class-based test (use functions)",
    ),
]


def collect_auto_signals(files: list[Path]) -> list[str]:
    """Return definitive violation strings for files that match automated rules.

    Excludes .github/ harness files — those are meta-tools, not application code.
    """
    signals = []
    for py_file in files:
        if not py_file.suffix == ".py":
            continue
        # Skip harness scripts — they intentionally reference forbidden patterns
        if py_file.is_relative_to(CLAUDE_DIR) or py_file.is_relative_to(Path(".github")):
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


def check_token_budget() -> None:
    """Check token budget for all harness files."""
    for pattern in [
        "rules/*.md",
        "skills/*/SKILL.md",
    ]:
        for f in sorted(CLAUDE_DIR.glob(pattern)):
            t = approx_tokens(f)
            if t > TOKEN_BUDGET:
                rel = str(f.relative_to(CLAUDE_DIR))
                structural_issues.append(
                    f"**{rel}**: ~{t} tokens (budget: {TOKEN_BUDGET}) — trim or split"
                )


# ── 2. Duplicate prompt↔skill detection ───────────────────────────────────────


def check_duplicate_rules() -> None:
    """Detect duplicate rule↔skill pairs or rule↔CLAUDE.md overlaps."""
    # In Claude Code, duplicates are rules that overlap with CLAUDE.md content
    # This is a placeholder — Claude Code doesn't have prompt↔skill duality
    pass


# ── 2b. Token efficiency metrics ──────────────────────────────────────────────

# Patterns that are always loaded for most tasks (broad applyTo globs)
_ALWAYS_LOADED_GLOBS = {"**/*", "**/*.py"}


def _count_rules(path: Path) -> int:
    """Count enforceable rules in a harness file (heuristic: list items with keywords)."""
    text = path.read_text("utf-8")
    # Count lines that look like rules: "- **...**", "| ... |", or bullet points with
    # imperative verbs / forbidden patterns
    rule_patterns = [
        re.compile(r"^-\s+\*\*", re.MULTILINE),  # bold bullet items
        re.compile(r"^\|\s*`[^`]+`\s*\|", re.MULTILINE),  # table rows with code
        re.compile(
            r"^-\s+(?:금지|반드시|사용|절대|forbidden)", re.MULTILINE | re.IGNORECASE
        ),
    ]
    lines = set()
    for pat in rule_patterns:
        for m in pat.finditer(text):
            lines.add(text[: m.start()].count("\n"))
    return max(len(lines), 1)  # at least 1 to avoid division by zero


def build_token_efficiency_section() -> str:
    """Build the Token Efficiency section with per-file metrics."""
    rows: list[str] = []
    always_loaded_total = 0

    instructions = parse_instruction_files()

    # Also include root CLAUDE.md (always loaded)
    claude_md = Path("CLAUDE.md")
    all_files: list[tuple[str, str, Path]] = []
    if claude_md.exists():
        all_files.append(("**/*", "CLAUDE.md", claude_md))
    all_files.extend(instructions)

    for glob, name, path in all_files:
        tokens = approx_tokens(path)
        rules = _count_rules(path)
        density = tokens / rules
        is_always = glob in _ALWAYS_LOADED_GLOBS
        if is_always:
            always_loaded_total += tokens

        # Grade
        if density <= 30:
            grade = "✅"
        elif density <= 60:
            grade = "⚠️"
        else:
            grade = "❌"

        load = "always" if is_always else "on-demand"
        rows.append(
            f"| `{name}` | {tokens} | {rules} | {density:.0f} | {grade} | {load} |"
        )

    # Always-loaded total grade
    if always_loaded_total <= 3000:
        total_grade = "✅"
    elif always_loaded_total <= 5000:
        total_grade = "⚠️"
    else:
        total_grade = "❌"

    out: list[str] = ["## Token Efficiency\n\n"]
    out.append("| File | Tokens | Rules | Tok/Rule | Grade | Load |\n")
    out.append("|------|--------|-------|----------|-------|------|\n")
    out.extend(f"{r}\n" for r in rows)
    out.append(
        f"\n**Always-loaded total**: ~{always_loaded_total} tokens {total_grade}\n"
    )
    out.append("(threshold: ≤3000 ✅, ≤5000 ⚠️, >5000 ❌)\n\n")
    return "".join(out)


# ── 3. Build AI compliance evaluation scaffold ────────────────────────────────


def run_review(scope: Scope) -> None:
    """Run the harness review with the specified scope."""
    global structural_issues
    structural_issues = []

    # 1. Token budget check
    check_token_budget()

    # 2. Duplicate detection
    check_duplicate_rules()

    # 3. Build AI compliance evaluation scaffold
    changed_files = get_session_changed_files(scope)
    py_files = [f for f in changed_files if f.suffix == ".py"]

    instructions = parse_instruction_files()
    file_rule_map = map_files_to_instructions(py_files, instructions)
    auto_signals = collect_auto_signals(py_files)

    # Only include files that have applicable instructions in the diff
    diff_candidates = [f for f in py_files if f in file_rule_map]
    diff_text = get_session_diff(diff_candidates, scope)

    # 4. Harness-change evaluation scaffold
    # Harness files are .claude/**/*.md, CLAUDE.md, and .claude/hooks/*.py
    harness_changed: list[Path] = []
    for f in changed_files:
        # Check root CLAUDE.md
        if f == Path("CLAUDE.md"):
            harness_changed.append(f)
            continue
        # Check .claude/ directory files
        try:
            rel = f.relative_to(CLAUDE_DIR)
        except ValueError:
            continue
        if str(rel) == "hooks/harness-review.md":
            continue  # skip the generated report itself
        if f.suffix in (".md", ".py", ".json"):
            harness_changed.append(f)

    harness_diff = get_session_diff(harness_changed, scope)

    # 5. Write report
    token_efficiency_section = build_token_efficiency_section()
    _write_report(
        scope,
        file_rule_map,
        auto_signals,
        diff_text,
        harness_changed,
        harness_diff,
        token_efficiency_section,
    )


def _write_report(
    scope: Scope,
    file_rule_map: dict[Path, list[str]],
    auto_signals: list[str],
    diff_text: str,
    harness_changed: list[Path],
    harness_diff: str,
    token_efficiency_section: str,
) -> None:
    """Write the harness review report."""
    has_structural = bool(structural_issues)
    has_py_changes = bool(file_rule_map)
    has_harness_changes = bool(harness_changed)

    scope_label = f" (scope: {scope})" if scope != "branch" else ""

    if has_structural or has_py_changes or auto_signals or has_harness_changes:
        out: list[str] = [f"# Harness Meta-Review Report{scope_label}\n\n"]

        # Structural issues (automated, deterministic)
        if has_structural:
            out.append("## Structural Issues\n\n")
            out += [f"- {i}\n" for i in structural_issues]
            out.append("\n_Resolve these to keep context-window usage efficient._\n\n")

        # Token efficiency metrics (always included)
        out.append(token_efficiency_section)

        # AI compliance evaluation scaffold for source code
        if has_py_changes or auto_signals:
            out.append("## Source Code Compliance\n\n")
            out.append(
                "> **Action required (AI agent):** Evaluate the changed files "
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
                out.append(
                    "\n_These are certain violations — fix regardless of AI assessment._\n\n"
                )

            # Embedded diff
            if diff_text:
                out.append("### Session Diff (for AI review)\n\n")
                out.append("```diff\n")
                out.append(diff_text + "\n")
                out.append("```\n\n")

            out.append("### Evaluation Prompt\n\n")
            out.append(
                "For each file in the table above, assess compliance with its listed instructions "
                "by reviewing the diff. For each file provide:\n\n"
                "1. **Grade**: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL\n"
                "2. **Observations**: Key compliance strengths and gaps (max 3 bullets)\n"
                "3. **Suggestions**: Specific improvements if PARTIAL or FAIL\n\n"
                "Then give an overall session compliance grade and a 1-sentence summary.\n"
            )

        # AI evaluation scaffold for harness-file changes
        if has_harness_changes:
            out.append("## Harness Quality Evaluation\n\n")
            out.append(
                "> **Action required (AI agent):** The harness itself changed "
                "this session. Evaluate the quality of those changes against these criteria:\n\n"
                "> - **Clarity**: Are rules unambiguous and actionable?\n"
                "> - **Token efficiency**: No redundancy, minimal prose, within 900-token budget?\n"
                "> - **Coverage completeness**: Do the changed files cover the intended scope "
                "without gaps or overlaps with other harness files?\n"
                "> - **Structural soundness**: Correct frontmatter/format for file type "
                "(instructions / skill / hook / prompt)?\n\n"
            )
            out.append("### Changed Harness Files\n\n")
            out += [f"- `{f}`\n" for f in sorted(harness_changed)]
            out.append("\n")

            if harness_diff:
                out.append("### Harness Diff (for AI review)\n\n")
                out.append("```diff\n")
                out.append(harness_diff + "\n")
                out.append("```\n\n")

            out.append("### Evaluation Prompt\n\n")
            out.append(
                "For each changed harness file, assess quality on the four criteria above. "
                "For each file provide:\n\n"
                "1. **Grade**: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL\n"
                "2. **Observations**: Key strengths and gaps (max 3 bullets)\n"
                "3. **Suggestions**: Specific improvements if PARTIAL or FAIL\n\n"
                "Then give an overall harness quality grade and a 1-sentence summary.\n"
            )

        REPORT.write_text("".join(out), "utf-8")
        total = len(structural_issues) + len(auto_signals)
        file_count = len(file_rule_map)
        print(
            f"[harness-review] report written{scope_label} — {total} automated issue(s),"
            f" {file_count} source file(s) + {len(harness_changed)} harness file(s)"
            f" queued for AI evaluation — see {REPORT}"
        )
        for i in structural_issues:
            print(f"  [structural] {i}")
        for s in auto_signals:
            print(f"  [auto-signal] {s}")
    else:
        REPORT.unlink(missing_ok=True)
        print(
            f"[harness-review] No issues found{scope_label}. "
            "No files with applicable harness rules changed."
        )


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Harness meta-review: token budget, duplicate detection, and AI compliance scaffold.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scopes:
  branch    Compare against base branch (default) — all commits in current branch
  worktree  Only uncommitted changes (staged + unstaged vs HEAD)
  session   Changes since 'start' command was run (requires session marker)

Session workflow:
  python harness-review.py start           # Mark session start
  # ... do work ...
  python harness-review.py --scope session # Review session changes only
  python harness-review.py end             # Clear session marker
""",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "end"],
        help="Session management: 'start' to mark session begin, 'end' to clear marker",
    )
    parser.add_argument(
        "--scope",
        choices=["branch", "worktree", "session"],
        default="branch",
        help="Scope of changes to review (default: branch)",
    )

    args = parser.parse_args()

    if args.command == "start":
        start_session()
    elif args.command == "end":
        end_session()
    else:
        run_review(args.scope)


if __name__ == "__main__":
    main()
