# Harness Meta-Review Report

## Source Code Compliance

> **Action required (AI agent):** Evaluate the changed files below against all applicable harness rules. Provide a holistic qualitative assessment — consider naming, patterns, type safety, structure, DDD/AOP/plugin conventions, and anything else covered by the applicable instructions.

### Changed Files & Applicable Rules

| File | Applicable Instructions |
|------|--------------------------|
| `.github/hooks/harness-review.py` | `api-reference`, `python-code` |

### Session Diff (for AI review)

```diff
diff --git a/.github/hooks/harness-review.py b/.github/hooks/harness-review.py
new file mode 100644
index 0000000..168f4ce
--- /dev/null
+++ b/.github/hooks/harness-review.py
@@ -0,0 +1,379 @@
+#!/usr/bin/env python3
+"""Harness meta-review: token budget, duplicate detection, and AI compliance scaffold.
+
+Architecture
+------------
+This script runs at sessionEnd (non-AI shell context). It performs automated
+structural checks and prepares a rich evaluation scaffold for the AI agent.
+
+The AI-driven qualitative evaluation is performed by the agent itself via the
+`harness-review` skill, which the agent invokes as the FINAL step of every
+coding session (mandated by the agent spec). The skill reads this script's
+output and performs holistic qualitative assessment of all session changes
+against applicable harness rules.
+
+Responsibilities of this script (automated, deterministic):
+1. Token budget per harness file — flags files exceeding 900-token budget
+2. Duplicate prompt↔skill pairs — same workflow defined in both directories
+3. AI compliance evaluation scaffold for source code — for changed Python files:
+   - Maps each file to its applicable instruction files (via applyTo: globs)
+   - Embeds a condensed git diff for those files
+   - Lists automated signals (definitive rule violations detectable by regex)
+   - Writes a structured evaluation prompt for the AI skill to assess compliance
+4. AI evaluation scaffold for harness-file changes:
+   - Lists which harness files changed this session
+   - Embeds their diffs for AI review
+   - Writes a quality evaluation prompt (clarity, token efficiency, coverage, structure)
+
+All findings are written to harness-review.md and consumed by the
+`harness-review` skill when the agent invokes it.
+"""
+
+import re
+import subprocess
+from pathlib import Path
+
+GITHUB = Path(".github")
+TOKEN_BUDGET = 900          # approx tokens (chars / 4) per harness file
+DIFF_LINE_BUDGET = 200      # max diff lines to embed (avoid token bloat)
+REPORT = GITHUB / "hooks" / "harness-review.md"
+
+structural_issues: list[str] = []
+
+
+# ── helpers ──────────────────────────────────────────────────────────────────
+
+def approx_tokens(p: Path) -> int:
+    return len(p.read_text("utf-8")) // 4
+
+
+def _find_base_ref() -> str:
+    """Return the merge-base SHA for comparison, trying several candidates."""
+    candidates = ["origin/HEAD", "origin/develop", "origin/main", "origin/master"]
+    for ref in candidates:
+        result = subprocess.run(
+            ["git", "merge-base", "HEAD", ref],
+            capture_output=True, text=True,
+        )
+        if result.returncode == 0 and result.stdout.strip():
+            return result.stdout.strip()
+    # Last resort: first commit reachable from HEAD that is NOT in current branch
+    result = subprocess.run(
+        ["git", "log", "--oneline", "--first-parent", "HEAD"],
+        capture_output=True, text=True,
+    )
+    lines = result.stdout.strip().splitlines()
+    if len(lines) > 1:
+        return lines[-1].split()[0]  # oldest commit SHA
+    return ""
+
+
+def get_session_changed_files() -> list[Path]:
+    """Files changed in this session vs the base branch (existing files only)."""
+    try:
+        base = _find_base_ref()
+        if not base:
+            return []
+        out = subprocess.run(
+            ["git", "diff", "--name-only", base],
+            capture_output=True, text=True, check=True,
+        ).stdout
+        return [Path(f) for f in out.splitlines() if Path(f).exists()]
+    except Exception:
+        return []
+
+
+def get_session_diff(files: list[Path]) -> str:
+    """Return a condensed unified diff for the given files, capped at DIFF_LINE_BUDGET lines."""
+    if not files:
+        return ""
+    try:
+        base = _find_base_ref()
+        if not base:
+            return ""
+        out = subprocess.run(
+            ["git", "diff", base, "--", *[str(f) for f in files]],
+            capture_output=True, text=True,
+        ).stdout
+        lines = out.splitlines()
+        if len(lines) > DIFF_LINE_BUDGET:
+            lines = lines[:DIFF_LINE_BUDGET] + [f"... [{len(lines) - DIFF_LINE_BUDGET} lines truncated]"]
+        return "\n".join(lines)
+    except Exception:
+        return ""
+
+
+def parse_instruction_files() -> list[tuple[str, str, Path]]:
+    """Return [(apply_to_glob, name, path)] for all instruction files."""
+    result = []
+    for f in sorted((GITHUB / "instructions").glob("*.instructions.md")):
+        text = f.read_text("utf-8")
+        m = re.search(r'^applyTo:\s*["\']?([^"\'>\n]+)["\']?', text, re.MULTILINE)
+        if m:
+            name = f.stem.removesuffix(".instructions")
+            result.append((m.group(1).strip(), name, f))
+    return result
+
+
+def _glob_to_regex(glob: str) -> re.Pattern[str]:
+    """Convert a glob pattern with ** support to a compiled regex."""
+    # Tokenize to avoid mangling ** when replacing *
+    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob)
+    result = []
+    for part in parts:
+        if part == "**/":
+            result.append("(.*/)?")
+        elif part == "**":
+            result.append(".*")
+        elif part == "*":
+            result.append("[^/]*")
+        elif part == "?":
+            result.append("[^/]")
+        else:
+            result.append(re.escape(part))
+    return re.compile("".join(result))
+
+
+def map_files_to_instructions(
+    files: list[Path],
+    instructions: list[tuple[str, str, Path]],
+) -> dict[Path, list[str]]:
+    """Return {file: [instruction_name, ...]} for each changed file."""
+    compiled = [(glob, name, _glob_to_regex(glob)) for glob, name, _ in instructions]
+    mapping: dict[Path, list[str]] = {}
+    for f in files:
+        applicable = [
+            name for glob, name, rx in compiled
+            if re.fullmatch(rx, str(f)) or re.fullmatch(rx, f.name)
+        ]
+        if applicable:
+            mapping[f] = applicable
+    return mapping
+
+
+# ── automated signals: definitive regex-detectable violations ─────────────────
+
+_AUTO_SIGNALS: list[tuple[re.Pattern[str], str, str]] = [
+    (re.compile(r"#\s*type:\s*ignore"), "python-code §Type Safety", "`# type: ignore` is forbidden"),
+    (re.compile(r"^class\s+Test\w*[:(]", re.MULTILINE), "test-writing §Structure", "class-based test (use functions)"),
+]
+
+
+def collect_auto_signals(files: list[Path]) -> list[str]:
+    """Return definitive violation strings for files that match automated rules.
+
+    Excludes .github/ harness files — those are meta-tools, not application code.
+    """
+    signals = []
+    for py_file in files:
+        if not py_file.suffix == ".py":
+            continue
+        # Skip harness scripts — they intentionally reference forbidden patterns
+        if py_file.is_relative_to(GITHUB):
+            continue
+        try:
+            content = py_file.read_text("utf-8")
+        except Exception:
+            continue
+        for pattern, rule_ref, desc in _AUTO_SIGNALS:
+            for m in pattern.finditer(content):
+                lineno = content[: m.start()].count("\n") + 1
+                signals.append(f"`{py_file}` line {lineno} — {desc} (**{rule_ref}**)")
+    return signals
+
+
+# ── 1. Token budget check ─────────────────────────────────────────────────────
+
+for pattern in [
+    "instructions/*.instructions.md",
+    "prompts/*.prompt.md",
+    "skills/*/SKILL.md",
+]:
+    for f in sorted(GITHUB.glob(pattern)):
+        t = approx_tokens(f)
+        if t > TOKEN_BUDGET:
... [185 lines truncated]
```

### Evaluation Prompt

For each file in the table above, assess compliance with its listed instructions by reviewing the diff. For each file provide:

1. **Grade**: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL
2. **Observations**: Key compliance strengths and gaps (max 3 bullets)
3. **Suggestions**: Specific improvements if PARTIAL or FAIL

Then give an overall session compliance grade and a 1-sentence summary.
## Harness Quality Evaluation

> **Action required (AI agent):** The harness itself changed this session. Evaluate the quality of those changes against these criteria:

> - **Clarity**: Are rules unambiguous and actionable?
> - **Token efficiency**: No redundancy, minimal prose, within 900-token budget?
> - **Coverage completeness**: Do the changed files cover the intended scope without gaps or overlaps with other harness files?
> - **Structural soundness**: Correct frontmatter/format for file type (instructions / skill / hook / prompt)?

### Changed Harness Files

- `.github/copilot-instructions.md`
- `.github/hooks/harness-review.py`
- `.github/hooks/hooks.json`
- `.github/instructions/api-reference.instructions.md`
- `.github/instructions/aspect.instructions.md`
- `.github/instructions/domain.instructions.md`
- `.github/instructions/plugin.instructions.md`
- `.github/instructions/python-code.instructions.md`
- `.github/instructions/test-writing.instructions.md`
- `.github/prompts/harness-update.prompt.md`
- `.github/skills/create-plugin/SKILL.md`
- `.github/skills/harness-review/SKILL.md`
- `.github/skills/improve-coverage/SKILL.md`
- `.github/skills/review-pr/SKILL.md`

### Harness Diff (for AI review)

```diff
diff --git a/.github/copilot-instructions.md b/.github/copilot-instructions.md
index 2c79e23..e96890d 100644
--- a/.github/copilot-instructions.md
+++ b/.github/copilot-instructions.md
@@ -10,6 +10,8 @@
 | Layer | 위치 | 역할 |
 |-------|------|------|
 | Custom Agent | `.github/agents/spakky-dev.agent.md` | 도구 제한, 행동 규칙 |
+| Hooks | `.github/hooks/hooks.json` | 세션 수명주기 자동 실행 (`sessionStart`: uv sync / `sessionEnd`: 정량 평가) |
+| Skills | `.github/skills/*/SKILL.md` | 재사용 가능한 에이전트 스킬 |
 | File Instructions | `.github/instructions/*.instructions.md` | 파일 패턴별 자동 적용 규칙 |
 | Prompt Files | `.github/prompts/*.prompt.md` | 반복 작업 워크플로우 |
 
@@ -22,7 +24,17 @@ Spring-inspired DI/IoC framework for Python 3.11+ with AOP and plugin system. Us
 - **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`
 - **Plugins** (`plugins/`): `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`
 
-**API Reference**: `.github/instructions/api-reference.instructions.md` (Python 파일 작성 시 자동 적용)
+**자동 적용 인스트럭션 (파일 패턴별)**:
+
+| 파일 패턴 | 인스트럭션 | 내용 |
+|-----------|-----------|------|
+| `**/*.py` | `api-reference`, `python-code` | API 레퍼런스, 타입/네이밍 표준 |
+| `**/tests/**/*.py` | `test-writing` | 테스트 구조, 네이밍, TDD |
+| `**/error.py` | `error-classes` | 에러 클래스 계층 구조 |
+| `**/domain/**/*.py` | `domain` | DDD 빌딩 블록 패턴 |
+| `**/aspects/**/*.py` | `aspect` | AOP Aspect 구조 패턴 |
+| `plugins/**/*.py` | `plugin` | 플러그인 개발 규칙 |
+| `**/pyproject.toml` | `monorepo` | 모노레포 도구 실행 원칙 |
 
 ## Monorepo Rules
 
diff --git a/.github/hooks/harness-review.py b/.github/hooks/harness-review.py
new file mode 100644
index 0000000..168f4ce
--- /dev/null
+++ b/.github/hooks/harness-review.py
@@ -0,0 +1,379 @@
+#!/usr/bin/env python3
+"""Harness meta-review: token budget, duplicate detection, and AI compliance scaffold.
+
+Architecture
+------------
+This script runs at sessionEnd (non-AI shell context). It performs automated
+structural checks and prepares a rich evaluation scaffold for the AI agent.
+
+The AI-driven qualitative evaluation is performed by the agent itself via the
+`harness-review` skill, which the agent invokes as the FINAL step of every
+coding session (mandated by the agent spec). The skill reads this script's
+output and performs holistic qualitative assessment of all session changes
+against applicable harness rules.
+
+Responsibilities of this script (automated, deterministic):
+1. Token budget per harness file — flags files exceeding 900-token budget
+2. Duplicate prompt↔skill pairs — same workflow defined in both directories
+3. AI compliance evaluation scaffold for source code — for changed Python files:
+   - Maps each file to its applicable instruction files (via applyTo: globs)
+   - Embeds a condensed git diff for those files
+   - Lists automated signals (definitive rule violations detectable by regex)
+   - Writes a structured evaluation prompt for the AI skill to assess compliance
+4. AI evaluation scaffold for harness-file changes:
+   - Lists which harness files changed this session
+   - Embeds their diffs for AI review
+   - Writes a quality evaluation prompt (clarity, token efficiency, coverage, structure)
+
+All findings are written to harness-review.md and consumed by the
+`harness-review` skill when the agent invokes it.
+"""
+
+import re
+import subprocess
+from pathlib import Path
+
+GITHUB = Path(".github")
+TOKEN_BUDGET = 900          # approx tokens (chars / 4) per harness file
+DIFF_LINE_BUDGET = 200      # max diff lines to embed (avoid token bloat)
+REPORT = GITHUB / "hooks" / "harness-review.md"
+
+structural_issues: list[str] = []
+
+
+# ── helpers ──────────────────────────────────────────────────────────────────
+
+def approx_tokens(p: Path) -> int:
+    return len(p.read_text("utf-8")) // 4
+
+
+def _find_base_ref() -> str:
+    """Return the merge-base SHA for comparison, trying several candidates."""
+    candidates = ["origin/HEAD", "origin/develop", "origin/main", "origin/master"]
+    for ref in candidates:
+        result = subprocess.run(
+            ["git", "merge-base", "HEAD", ref],
+            capture_output=True, text=True,
+        )
+        if result.returncode == 0 and result.stdout.strip():
+            return result.stdout.strip()
+    # Last resort: first commit reachable from HEAD that is NOT in current branch
+    result = subprocess.run(
+        ["git", "log", "--oneline", "--first-parent", "HEAD"],
+        capture_output=True, text=True,
+    )
+    lines = result.stdout.strip().splitlines()
+    if len(lines) > 1:
+        return lines[-1].split()[0]  # oldest commit SHA
+    return ""
+
+
+def get_session_changed_files() -> list[Path]:
+    """Files changed in this session vs the base branch (existing files only)."""
+    try:
+        base = _find_base_ref()
+        if not base:
+            return []
+        out = subprocess.run(
+            ["git", "diff", "--name-only", base],
+            capture_output=True, text=True, check=True,
+        ).stdout
+        return [Path(f) for f in out.splitlines() if Path(f).exists()]
+    except Exception:
+        return []
+
+
+def get_session_diff(files: list[Path]) -> str:
+    """Return a condensed unified diff for the given files, capped at DIFF_LINE_BUDGET lines."""
+    if not files:
+        return ""
+    try:
+        base = _find_base_ref()
+        if not base:
+            return ""
+        out = subprocess.run(
+            ["git", "diff", base, "--", *[str(f) for f in files]],
+            capture_output=True, text=True,
+        ).stdout
+        lines = out.splitlines()
+        if len(lines) > DIFF_LINE_BUDGET:
+            lines = lines[:DIFF_LINE_BUDGET] + [f"... [{len(lines) - DIFF_LINE_BUDGET} lines truncated]"]
+        return "\n".join(lines)
+    except Exception:
+        return ""
+
+
+def parse_instruction_files() -> list[tuple[str, str, Path]]:
+    """Return [(apply_to_glob, name, path)] for all instruction files."""
+    result = []
+    for f in sorted((GITHUB / "instructions").glob("*.instructions.md")):
+        text = f.read_text("utf-8")
+        m = re.search(r'^applyTo:\s*["\']?([^"\'>\n]+)["\']?', text, re.MULTILINE)
+        if m:
+            name = f.stem.removesuffix(".instructions")
+            result.append((m.group(1).strip(), name, f))
+    return result
+
+
+def _glob_to_regex(glob: str) -> re.Pattern[str]:
+    """Convert a glob pattern with ** support to a compiled regex."""
+    # Tokenize to avoid mangling ** when replacing *
+    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob)
+    result = []
+    for part in parts:
+        if part == "**/":
+            result.append("(.*/)?")
+        elif part == "**":
+            result.append(".*")
+        elif part == "*":
+            result.append("[^/]*")
+        elif part == "?":
+            result.append("[^/]")
+        else:
+            result.append(re.escape(part))
+    return re.compile("".join(result))
+
+
+def map_files_to_instructions(
+    files: list[Path],
+    instructions: list[tuple[str, str, Path]],
+) -> dict[Path, list[str]]:
+    """Return {file: [instruction_name, ...]} for each changed file."""
+    compiled = [(glob, name, _glob_to_regex(glob)) for glob, name, _ in instructions]
+    mapping: dict[Path, list[str]] = {}
+    for f in files:
+        applicable = [
+            name for glob, name, rx in compiled
+            if re.fullmatch(rx, str(f)) or re.fullmatch(rx, f.name)
+        ]
+        if applicable:
+            mapping[f] = applicable
+    return mapping
+
+
+# ── automated signals: definitive regex-detectable violations ─────────────────
+
+_AUTO_SIGNALS: list[tuple[re.Pattern[str], str, str]] = [
+    (re.compile(r"#\s*type:\s*ignore"), "python-code §Type Safety", "`# type: ignore` is forbidden"),
+    (re.compile(r"^class\s+Test\w*[:(]", re.MULTILINE), "test-writing §Structure", "class-based test (use functions)"),
+]
+
+
+def collect_auto_signals(files: list[Path]) -> list[str]:
... [1272 lines truncated]
```

### Evaluation Prompt

For each changed harness file, assess quality on the four criteria above. For each file provide:

1. **Grade**: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL
2. **Observations**: Key strengths and gaps (max 3 bullets)
3. **Suggestions**: Specific improvements if PARTIAL or FAIL

Then give an overall harness quality grade and a 1-sentence summary.
