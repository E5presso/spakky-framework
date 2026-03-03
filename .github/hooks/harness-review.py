#!/usr/bin/env python3
"""Harness meta-review: detect token bloat and duplicate content, surface improvements."""

from pathlib import Path

GITHUB = Path(".github")
TOKEN_BUDGET = 900  # approx tokens (chars / 4) per file
REPORT = GITHUB / "hooks" / "harness-review.md"

issues: list[str] = []


def approx_tokens(p: Path) -> int:
    return len(p.read_text("utf-8")) // 4


# 1. Token budget check
for pattern in [
    "instructions/*.instructions.md",
    "prompts/*.prompt.md",
    "skills/*/SKILL.md",
]:
    for f in sorted(GITHUB.glob(pattern)):
        t = approx_tokens(f)
        if t > TOKEN_BUDGET:
            rel = str(f.relative_to(GITHUB))
            issues.append(f"**{rel}**: ~{t} tokens (budget: {TOKEN_BUDGET}) — trim or split")

# 2. Duplicate prompt↔skill detection
PROMPT_DIR = GITHUB / "prompts"
SKILL_DIR = GITHUB / "skills"

if PROMPT_DIR.exists() and SKILL_DIR.exists():
    prompt_stems = {
        f.stem.removesuffix(".prompt"): f for f in PROMPT_DIR.glob("*.prompt.md")
    }
    skill_dirs = {d.name: d for d in SKILL_DIR.iterdir() if d.is_dir()}

    # Known alias pairs (prompt-name → skill-folder-name)
    alias_pairs = [
        ("coverage", "improve-coverage"),
        ("plugin", "create-plugin"),
        ("review", "review-pr"),
    ]
    for pname, sname in alias_pairs:
        if pname in prompt_stems and sname in skill_dirs:
            issues.append(
                f"**prompts/{pname}.prompt.md** duplicates **skills/{sname}/SKILL.md**"
                " — remove prompt, keep skill"
            )

    # Generic: check if any prompt name exactly matches a skill folder
    for pname, pfile in prompt_stems.items():
        if pname in skill_dirs:
            issues.append(
                f"**prompts/{pname}.prompt.md** duplicates **skills/{pname}/SKILL.md**"
                " — remove prompt, keep skill"
            )

# 3. Write or clear report
if issues:
    lines = ["# Harness Meta-Review — Improvement Suggestions\n\n"]
    lines += [f"- {i}\n" for i in issues]
    lines += ["\n_Resolve these issues to keep context-window usage efficient._\n"]
    REPORT.write_text("".join(lines), "utf-8")
    print(f"[harness-review] {len(issues)} issue(s) — see {REPORT}")
    for i in issues:
        print(f"  • {i}")
else:
    REPORT.unlink(missing_ok=True)
    print("[harness-review] No issues found.")
