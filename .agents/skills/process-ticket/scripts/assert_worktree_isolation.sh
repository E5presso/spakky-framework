#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 [--init] <issue-number>" >&2
}

fail() {
  echo "isolation-failed: $*" >&2
  exit 2
}

mode="check"
if [ "${1:-}" = "--init" ]; then
  mode="init"
  shift
fi

issue="${1:-}"
if [ -z "$issue" ]; then
  usage
  exit 2
fi

case "$issue" in
  \#*) issue="${issue#\#}" ;;
esac

worktree=$(git rev-parse --show-toplevel)
repo_root=$(git -C "$worktree" rev-parse --path-format=absolute --git-common-dir | xargs dirname)
state_file="$worktree/.process-state.json"

if [ "$worktree" = "$repo_root" ]; then
  fail "cwd-is-root worktree=$worktree"
fi

case "$worktree" in
  "$repo_root/.claude/worktrees/"*) ;;
  *) fail "unexpected-worktree-path worktree=$worktree expected-prefix=$repo_root/.claude/worktrees/" ;;
esac

branch=$(git -C "$worktree" branch --show-current)
case "$branch" in
  */"$issue") ;;
  *) fail "unexpected-branch branch=$branch expected-suffix=/$issue" ;;
esac

root_branch=$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)
if [ "$root_branch" != "develop" ]; then
  fail "root-branch branch=$root_branch expected=develop"
fi

root_head=$(git -C "$repo_root" rev-parse HEAD)
root_status=$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)
root_status_hash=$(printf '%s' "$root_status" | shasum -a 256 | awk '{print $1}')

if [ "$mode" = "init" ]; then
  if [ -n "$root_status" ]; then
    fail "root-dirty-at-phase3 status=$(printf '%s' "$root_status" | tr '\n' ';')"
  fi
  if [ ! -f "$state_file" ]; then
    fail "state-missing path=$state_file"
  fi
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq \
    --arg root "$repo_root" \
    --arg worktree "$worktree" \
    --arg root_branch "$root_branch" \
    --arg root_head "$root_head" \
    --arg root_status_hash "$root_status_hash" \
    --arg branch "$branch" \
    --arg t "$ts" \
    '.root_guard = {
      repo_root: $root,
      worktree: $worktree,
      root_branch: $root_branch,
      root_head: $root_head,
      root_status_hash: $root_status_hash,
      branch: $branch
    } | .updated_at = $t' \
    "$state_file" > "$state_file.tmp"
  mv "$state_file.tmp" "$state_file"
  echo "isolation-ok: initialized issue=$issue worktree=$worktree root=$repo_root"
  exit 0
fi

if [ ! -f "$state_file" ]; then
  fail "state-missing path=$state_file"
fi

root_guard_present=$(jq -r 'has("root_guard") and (.root_guard | type == "object")' "$state_file")
if [ "$root_guard_present" != "true" ]; then
  fail "root-guard-missing run-phase3-init"
fi

missing_fields=$(jq -r '
  ["repo_root", "worktree", "root_branch", "root_head", "root_status_hash", "branch"]
  | map(select(. as $k | ($root.root_guard | has($k)) | not))
  | join(",")
' --argjson root "$(cat "$state_file")" <<<"{}")
if [ -n "$missing_fields" ]; then
  fail "root-guard-incomplete missing=$missing_fields"
fi

expected_branch=$(jq -r '.root_guard.branch' "$state_file")
if [ "$expected_branch" != "$branch" ]; then
  fail "branch-changed current=$branch expected=$expected_branch"
fi

expected_root_branch=$(jq -r '.root_guard.root_branch' "$state_file")
if [ "$expected_root_branch" != "$root_branch" ]; then
  fail "root-branch-changed current=$root_branch expected=$expected_root_branch"
fi

expected_worktree=$(jq -r '.root_guard.worktree' "$state_file")
if [ "$expected_worktree" != "$worktree" ]; then
  fail "worktree-mismatch current=$worktree expected=$expected_worktree"
fi

expected_root=$(jq -r '.root_guard.repo_root' "$state_file")
if [ "$expected_root" != "$repo_root" ]; then
  fail "root-mismatch current=$repo_root expected=$expected_root"
fi

expected_root_head=$(jq -r '.root_guard.root_head' "$state_file")
if [ "$expected_root_head" != "$root_head" ]; then
  fail "root-head-changed current=$root_head expected=$expected_root_head"
fi

expected_status_hash=$(jq -r '.root_guard.root_status_hash' "$state_file")
if [ "$expected_status_hash" != "$root_status_hash" ]; then
  fail "root-status-changed status=$(printf '%s' "$root_status" | tr '\n' ';')"
fi

echo "isolation-ok: issue=$issue worktree=$worktree root-clean"
