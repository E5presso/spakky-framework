#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT_UNDER_TEST="$SCRIPT_DIR/ai_review_auto_approve.sh"

if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
  echo "FATAL: script not found at $SCRIPT_UNDER_TEST" >&2
  exit 1
fi

make_gh_mock() {
  local bin_dir="$1"
  local fixture_dir="$2"

  cat > "$bin_dir/gh" <<'EOF_GH'
#!/usr/bin/env bash
set -euo pipefail

case_name="${AI_REVIEW_TEST_CASE:?AI_REVIEW_TEST_CASE is required}"
case_dir="${AI_REVIEW_FIXTURE_DIR:?AI_REVIEW_FIXTURE_DIR is required}/$case_name"

if [ "${1:-}" = "api" ]; then
  shift
  while [ "${1:-}" = "-H" ]; do
    shift 2
  done
  endpoint="${1:-}"

  case "$endpoint" in
    repos/*/commits/*/pulls)
      cat "$case_dir/pulls.json"
      ;;
    repos/*/pulls/*/reviews)
      cat "$case_dir/reviews.json"
      ;;
    repos/*/pulls/*)
      cat "$case_dir/pull.json"
      ;;
    repos/*/commits/*/statuses)
      cat "$case_dir/statuses.json"
      ;;
    repos/*/collaborators/*/permission)
      cat "$case_dir/permission.json"
      ;;
    *)
      echo "unhandled gh api endpoint: $endpoint" >&2
      exit 1
      ;;
  esac
  exit 0
fi

if [ "${1:-}" = "pr" ] && [ "${2:-}" = "review" ]; then
  printf '%s\n' "$*" >> "$case_dir/approve.log"
  exit 0
fi

echo "unhandled gh command: $*" >&2
exit 1
EOF_GH

  chmod +x "$bin_dir/gh"
  export AI_REVIEW_FIXTURE_DIR="$fixture_dir"
}

write_common_case() {
  local case_dir="$1"
  local sha="${2:-abc123}"
  local head_repo="${3:-E5presso/spakky-framework}"
  local base_repo="${4:-E5presso/spakky-framework}"
  local role="${5:-admin}"
  local status_state="${6:-success}"
  local creator="${7:-E5presso}"
  local pull_head_sha="${8:-$sha}"

  mkdir -p "$case_dir"

  cat > "$case_dir/pulls.json" <<EOF_JSON
[
  {
    "number": 999,
    "state": "open",
    "head": {
      "sha": "$sha"
    }
  }
]
EOF_JSON

  cat > "$case_dir/pull.json" <<EOF_JSON
{
  "number": 999,
  "head": {
    "sha": "$pull_head_sha",
    "repo": {
      "full_name": "$head_repo"
    }
  },
  "base": {
    "repo": {
      "full_name": "$base_repo"
    }
  }
}
EOF_JSON

  cat > "$case_dir/statuses.json" <<EOF_JSON
[
  {
    "context": "ai-review",
    "state": "$status_state",
    "created_at": "2026-01-01T00:01:00Z",
    "creator": {
      "login": "$creator"
    }
  }
]
EOF_JSON

  cat > "$case_dir/permission.json" <<EOF_JSON
{
  "role_name": "$role"
}
EOF_JSON

  echo "[]" > "$case_dir/reviews.json"
}

run_case() {
  local case_name="$1"
  local expected_approval="$2"
  local expected_reason="$3"
  local tmpdir="$4"

  local output_file="$tmpdir/$case_name.step-output"
  rm -f "$tmpdir/$case_name/approve.log" "$output_file"

  PATH="$tmpdir/bin:/usr/bin:/bin" \
    AI_REVIEW_TEST_CASE="$case_name" \
    REPO="E5presso/spakky-framework" \
    STATUS_SHA="abc123" \
    STATUS_CONTEXT="ai-review" \
    STATUS_STATE="success" \
    GITHUB_STEP_OUTPUT="$output_file" \
    bash "$SCRIPT_UNDER_TEST" > "$tmpdir/$case_name.stdout" 2> "$tmpdir/$case_name.stderr"

  local approval_seen="false"
  if [ -f "$tmpdir/$case_name/approve.log" ]; then
    approval_seen="true"
  fi

  if [ "$approval_seen" != "$expected_approval" ]; then
    echo "FAIL [$case_name]: expected approval=$expected_approval actual=$approval_seen" >&2
    cat "$tmpdir/$case_name.stderr" >&2
    return 1
  fi

  if ! grep -q "^reason=$expected_reason$" "$output_file"; then
    echo "FAIL [$case_name]: expected reason=$expected_reason" >&2
    cat "$output_file" >&2
    cat "$tmpdir/$case_name.stderr" >&2
    return 1
  fi

  echo "OK [$case_name]"
}

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/bin"
make_gh_mock "$tmpdir/bin" "$tmpdir"

write_common_case "$tmpdir/approve"
write_common_case "$tmpdir/fork" "abc123" "contributor/spakky-framework" "E5presso/spakky-framework"
write_common_case "$tmpdir/low-role" "abc123" "E5presso/spakky-framework" "E5presso/spakky-framework" "write"
write_common_case "$tmpdir/stale" "abc123" "E5presso/spakky-framework" "E5presso/spakky-framework" "admin" "success" "E5presso" "def456"
write_common_case "$tmpdir/latest-failure" "abc123" "E5presso/spakky-framework" "E5presso/spakky-framework" "admin" "failure"
write_common_case "$tmpdir/already-approved"

cat > "$tmpdir/already-approved/reviews.json" <<'EOF_JSON'
[
  {
    "user": {
      "login": "github-actions[bot]"
    },
    "state": "APPROVED",
    "commit_id": "abc123"
  }
]
EOF_JSON

fail=0
run_case "approve" "true" "approved" "$tmpdir" || fail=1
run_case "fork" "false" "fork-pr" "$tmpdir" || fail=1
run_case "low-role" "false" "creator-role-not-admin-or-maintain" "$tmpdir" || fail=1
run_case "stale" "false" "stale-status" "$tmpdir" || fail=1
run_case "latest-failure" "false" "latest-ai-review-status-not-success" "$tmpdir" || fail=1
run_case "already-approved" "false" "already-approved-by-bot" "$tmpdir" || fail=1

if [ "$fail" -ne 0 ]; then
  echo "test_ai_review_auto_approve.sh: FAIL" >&2
  exit 1
fi

echo "test_ai_review_auto_approve.sh: OK"
