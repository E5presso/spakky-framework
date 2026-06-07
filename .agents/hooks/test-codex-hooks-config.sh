#!/usr/bin/env bash
# Validates Codex hook config uses shared .agents hook scripts.

set -u

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
hooks_json="$repo_root/.codex/hooks.json"
hooks_symlink="$repo_root/.codex/hooks"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -f "$hooks_json" ] || fail "missing $hooks_json"
[ -L "$hooks_symlink" ] || fail "missing .codex/hooks symlink"
[ "$(readlink "$hooks_symlink")" = "../.agents/hooks" ] || fail ".codex/hooks must point to ../.agents/hooks"

jq empty "$hooks_json" >/dev/null || fail "hooks.json is not valid JSON"

if grep -qE 'CLAUDE_PROJECT_DIR|~/\\.claude|/\\.claude/hooks' "$hooks_json"; then
  fail "hooks.json must not call scripts through Claude-specific paths"
fi

if ! jq -e '
  def commands:
    [.. | objects | select(.type? == "command") | .command];
  def pre_tool_matchers:
    [.hooks.PreToolUse[]?.matcher];

  commands as $commands
  | pre_tool_matchers as $pre_tool_matchers
  | ($pre_tool_matchers | any(test("apply_patch"))) and
    ($commands | any(test("/\\.codex/hooks/check-worktree-isolation\\.sh"))) and
    ($commands | any(test("/\\.codex/hooks/check-python-edit\\.sh"))) and
    ($commands
      | map(select(test("check-(worktree-isolation|python-edit)\\.sh")))
      | all(test("/\\.codex/hooks/")))
' "$hooks_json" >/dev/null; then
  fail "shared hook scripts must be called through .codex/hooks"
fi

echo "PASS: Codex hook config uses shared hook paths"
