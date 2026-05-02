#!/usr/bin/env bash
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
exec "$repo_root/.agents/harness/skills/monitor-pr/scripts/watch.sh" "$@"
