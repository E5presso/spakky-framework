#!/usr/bin/env bash
# Smoke tests for check-worktree-isolation.sh.

set -u

HOOK="$(cd "$(dirname "$0")" && pwd)/check-worktree-isolation.sh"
if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable at $HOOK" >&2
  exit 1
fi

raw_dir="$(mktemp -d -t spakky-hook-test-XXXXXX)"
trap 'rm -rf "$raw_dir"' EXIT
work_dir="$(cd "$raw_dir" && pwd -P)"

repo="$work_dir/repo"
mkdir -p "$repo"
(
  cd "$repo"
  git init -q -b develop
  git config user.email test@example.com
  git config user.name test
  mkdir -p .claude/worktrees
  echo seed > seed.txt
  git add seed.txt
  git commit -q -m "seed"
  git worktree add -q .claude/worktrees/wt-a -b wt-a develop
  git worktree add -q .claude/worktrees/wt-b -b wt-b develop
) >/dev/null

wt_a="$repo/.claude/worktrees/wt-a"
wt_b="$repo/.claude/worktrees/wt-b"

pass=0
fail=0

run_case() {
  local desc="$1" cwd="$2" stdin="$3" expect="$4"
  local actual rc
  actual="$(cd "$cwd" && printf '%s' "$stdin" | "$HOOK" 2>/dev/null; echo $?)"
  rc="${actual##*$'\n'}"
  if [ "$rc" = "$expect" ]; then
    printf 'PASS  %s (rc=%s)\n' "$desc" "$rc"
    pass=$((pass + 1))
  else
    printf 'FAIL  %s (rc=%s, expected=%s)\n' "$desc" "$rc" "$expect"
    fail=$((fail + 1))
  fi
}

mk_edit() {
  local path="$1"
  jq -n --arg p "$path" '{tool_name:"Edit", tool_input:{file_path:$p}}'
}

mk_apply_patch() {
  local cwd="$1" path="$2"
  local cmd
  cmd="*** Begin Patch
*** Update File: $path
@@
+hook parser fixture
*** End Patch"
  jq -n --arg cwd "$cwd" --arg c "$cmd" '{cwd:$cwd, tool_name:"apply_patch", tool_input:{command:$c}}'
}

mk_exec_command() {
  local cmd="$1"
  jq -n --arg c "$cmd" '{tool_name:"exec_command", tool_input:{cmd:$c}}'
}

mk_exec_command_workdir() {
  local cmd="$1" workdir="$2"
  jq -n --arg c "$cmd" --arg workdir "$workdir" '{tool_name:"exec_command", tool_input:{cmd:$c, workdir:$workdir}}'
}

run_case "Edit inside worktree -> allow" \
  "$wt_a" "$(mk_edit "$wt_a/core.py")" 0

run_case "Edit on root checkout -> deny" \
  "$wt_a" "$(mk_edit "$repo/core.py")" 2

run_case "Edit outside repo -> allow" \
  "$wt_a" "$(mk_edit "/tmp/spakky-anywhere.py")" 0

run_case "Edit on wt-a from sibling cwd -> allow" \
  "$wt_b" "$(mk_edit "$wt_a/core.py")" 0

run_case "apply_patch relative path from root -> deny" \
  "$repo" "$(mk_apply_patch "$repo" "core.py")" 2

run_case "apply_patch relative path from worktree -> allow" \
  "$wt_a" "$(mk_apply_patch "$wt_a" "core.py")" 0

run_case "apply_patch parent traversal -> deny" \
  "$wt_a" "$(mk_apply_patch "$wt_a" "../../../seed.txt")" 2

run_case "exec_command touching root absolute path -> deny" \
  "$wt_a" "$(mk_exec_command "touch $repo/root.py")" 2

run_case "exec_command root workdir relative mutation -> deny" \
  "$wt_a" "$(mk_exec_command_workdir "touch root.py" "$repo")" 2

run_case "exec_command worktree workdir relative mutation -> allow" \
  "$wt_b" "$(mk_exec_command_workdir "touch worktree.py" "$wt_a")" 0

run_case "exec_command explicit cd into worktree from root workdir -> allow" \
  "$wt_b" "$(mk_exec_command_workdir "(cd $wt_a && touch worktree.py)" "$repo")" 0

run_case "exec_command git -C worktree then root mutation -> deny" \
  "$wt_b" "$(mk_exec_command_workdir "git -C $wt_a status && touch root.py" "$repo")" 2

if [ "$fail" -ne 0 ]; then
  echo "FAIL: $fail failed, $pass passed" >&2
  exit 1
fi

echo "PASS: worktree isolation hook ($pass cases)"
