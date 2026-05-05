#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <issue-number> [apply_patch-args...]" >&2
}

fail() {
  echo "safe-apply-patch-failed: $*" >&2
  exit 2
}

issue="${1:-}"
if [ -z "$issue" ]; then
  usage
  exit 2
fi
shift

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
guard="$script_dir/assert_worktree_isolation.sh"

if [ ! -x "$guard" ]; then
  fail "guard-not-executable path=$guard"
fi

"$guard" "$issue" >&2

if ! command -v apply_patch >/dev/null 2>&1; then
  fail "apply_patch-command-not-found"
fi

apply_patch "$@"

"$guard" "$issue" >&2
