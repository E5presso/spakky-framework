#!/usr/bin/env bash
# Verifies that monitor cache drift ignores informational bots while retaining actionable reviews.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
watch_sh="$script_dir/watch.sh"

run_case() {
  local fake_case="$1" expected_reason="$2" expected_stale_id="${3:-}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp_dir'" RETURN

  mkdir -p "$tmp_dir/bin"
  cat > "$tmp_dir/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "pr" ] && [ "${2:-}" = "view" ]; then
  cat <<'JSON'
{
  "mergeStateStatus": "BLOCKED",
  "reviewDecision": "REVIEW_REQUIRED",
  "statusCheckRollup": [
    {"name": "ci", "status": "IN_PROGRESS", "conclusion": null, "workflowName": "ci"}
  ],
  "comments": [],
  "state": "OPEN",
  "headRefOid": "abc123def456",
  "labels": []
}
JSON
  exit 0
fi

if [ "${1:-}" != "api" ]; then
  echo "unsupported gh invocation: $*" >&2
  exit 1
fi

case "${2:-}" in
  repos/*/pulls/*/comments)
    if [ "$FAKE_CASE" = "actionable" ]; then
      cat <<'JSON'
[{"id":201,"user":{"login":"chatgpt-codex-connector[bot]"},"body":"P1 feedback","created_at":"2026-08-01T00:00:00Z","updated_at":"2026-08-01T00:10:00Z"}]
JSON
    else
      printf '[]\n'
    fi
    ;;
  repos/*/issues/*/comments)
    cat <<'JSON'
[{"id":100,"user":{"login":"codecov[bot]"},"body":"Coverage report","created_at":"2026-08-01T00:00:00Z","updated_at":"2026-08-01T00:10:00Z"}]
JSON
    ;;
  repos/*/pulls/*/reviews)
    printf '[]\n'
    ;;
  repos/*/commits/*)
    printf '2026-08-01T00:00:00Z\n'
    ;;
  *)
    echo "unsupported gh api path: ${2:-}" >&2
    exit 1
    ;;
esac
SH
  chmod +x "$tmp_dir/bin/gh"

  cat > "$tmp_dir/bin/sleep" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$tmp_dir/bin/sleep"

  cat > "$tmp_dir/prev_state.json" <<'JSON'
{"ch1":{"201":"2026-08-01T00:00:00Z"},"ch2":{"100":"2026-08-01T00:00:00Z"},"ch3":{},"reviewDecision":"REVIEW_REQUIRED"}
JSON

  grep -v '^export PATH="/opt/homebrew/bin' "$watch_sh" > "$tmp_dir/watch_under_test.sh"
  FAKE_CASE="$fake_case" \
    MONITOR_PR_SCRIPTS_DIR="$script_dir" \
    PATH="$tmp_dir/bin:/usr/bin:/bin" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$tmp_dir/prev_state.json" \
    bash "$tmp_dir/watch_under_test.sh" > "$tmp_dir/stdout.log" 2> "$tmp_dir/stderr.log"

  grep -q "^reason=$expected_reason$" "$tmp_dir/stdout.log"
  if [ -n "$expected_stale_id" ]; then
    grep -q "^staleHandledIds=$expected_stale_id$" "$tmp_dir/stdout.log"
  fi
}

run_case informational heartbeat
run_case actionable comments-changed 201

echo "monitor-pr informational bot cache checks passed"
